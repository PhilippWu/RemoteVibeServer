#!/usr/bin/env bash
# =============================================================================
# install.sh — RemoteVibeServer bare-server installer
# =============================================================================
# One-liner usage:
#   curl -fsSL https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/install.sh | sudo bash
#
# The script resolves its configuration through a smart priority chain:
#
#   Path 1 — RVSconfig.yml already on disk (/etc/dev-server/ or ./)
#             → use it directly, skip all prompts
#
#   Path 2 — URL entered at the interactive prompt (http/https prefix)
#             → download with curl, validate, proceed
#
#   Path 3 — YAML content pasted at the interactive prompt (Ctrl-D to end)
#             → validate, proceed  [preserves current default behavior]
#
#   Path 4 — Empty Enter at the interactive prompt
#             → launch the embedded Bash setup wizard, write RVSconfig.yml
#
# After config resolution the script:
#   5. Parses the YAML into /etc/dev-server/env
#   6. Installs Docker, configures ufw + fail2ban
#   7. Downloads and executes the bootstrap → setup pipeline
#
# Requires: bash, curl (jq, unzip etc. are installed automatically)
# Designed for a fresh Ubuntu 22.04 / 24.04 server.
# Must be run as root.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_FILE="/etc/dev-server/env"
CONFIG_FILE="/etc/dev-server/RVSconfig.yml"
LOG_FILE="/var/log/dev-server-provision.log"
REPO_URL="https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/dev-server-provision"
PROVISION_DIR="/opt/dev-server-provision"

# ---------------------------------------------------------------------------
# Colours / helpers
# ---------------------------------------------------------------------------
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
RESET="\033[0m"

log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo -e "[$ts] [install] $*" | tee -a "$LOG_FILE"
}

die()     { echo -e "${RED}ERROR: $*${RESET}" >&2; exit 1; }
warn()    { echo -e "${YELLOW}⚠  $*${RESET}" >&2; }
success() { echo -e "${GREEN}✓  $*${RESET}"; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  die "This script must be run as root.  Usage:\n  curl -fsSL https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/install.sh | sudo bash"
fi

mkdir -p /etc/dev-server "$(dirname "$LOG_FILE")"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       RemoteVibeServer — Bare-Server Installer             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ---------------------------------------------------------------------------
# TTY helpers
# All interactive I/O goes through /dev/tty (fd 3) so the script works
# correctly even when stdin is a pipe (curl ... | bash).
# ---------------------------------------------------------------------------
exec 3</dev/tty

# Results are stored in these globals to avoid bash-scoping issues with
# local variables and subshell returns.
_TTY_LINE=""
_TTY_SECRET=""

_read_line() {
  # Usage: _read_line "prompt text"
  # Stores result in $_TTY_LINE.
  local prompt="${1:-}"
  [[ -n "$prompt" ]] && printf '%s' "$prompt" >/dev/tty
  _TTY_LINE=""
  IFS= read -r -u 3 _TTY_LINE || true
}

_read_secret() {
  # Usage: _read_secret "prompt text"
  # Reads without terminal echo; stores result in $_TTY_SECRET.
  local prompt="${1:-}"
  [[ -n "$prompt" ]] && printf '%s' "$prompt" >/dev/tty
  local _old_stty
  _old_stty="$(stty -g <&3 2>/dev/null || true)"
  stty -echo <&3 2>/dev/null || true
  _TTY_SECRET=""
  IFS= read -r -u 3 _TTY_SECRET || true
  if [[ -n "$_old_stty" ]]; then
    stty "$_old_stty" <&3 2>/dev/null || true
  else
    stty echo <&3 2>/dev/null || true
  fi
  echo >/dev/tty   # newline after hidden input
}

_read_confirm() {
  # Usage: _read_confirm "prompt [y/N]: " [default]
  # Returns 0 (true) for yes, 1 (false) for no.
  # Pass "y" as second arg to make yes the default.
  local prompt="${1:-}"
  local default="${2:-n}"
  _read_line "$prompt"
  local ans="${_TTY_LINE,,}"
  [[ -z "$ans" ]] && ans="${default,,}"
  [[ "$ans" == "y" || "$ans" == "yes" ]]
}

# ---------------------------------------------------------------------------
# YAML validation
# ---------------------------------------------------------------------------
_validate_yaml() {
  local content="$1"
  local label="${2:-Config}"
  if [[ -z "${content// /}" ]]; then
    die "$label is empty."
  fi
  # Must contain at least one recognisable key: value line
  if ! printf '%s\n' "$content" | grep -qE '^[a-zA-Z_][a-zA-Z0-9_]*:[[:space:]]'; then
    die "$label does not appear to be valid YAML (no 'key: value' pairs found)."
  fi
}

# ---------------------------------------------------------------------------
# Path 1 — detect existing RVSconfig.yml on disk
# ---------------------------------------------------------------------------
_find_config_on_disk() {
  # Prints the path of the first config file found; returns 1 if none found.
  local candidates=(
    "/etc/dev-server/RVSconfig.yml"
    "/etc/dev-server/RVSconfig.yaml"
    "./RVSconfig.yml"
    "./RVSconfig.yaml"
  )
  for f in "${candidates[@]}"; do
    if [[ -f "$f" ]]; then
      echo "$f"
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Path 2 — download config from a URL
# ---------------------------------------------------------------------------
_download_config() {
  local url="$1"
  log "Downloading config from: $url"
  local tmp curl_err
  tmp="$(mktemp)"
  curl_err="$(mktemp)"
  if ! curl -fsSL --max-time 60 "$url" -o "$tmp" 2>"$curl_err"; then
    local msg
    msg="$(cat "$curl_err" 2>/dev/null || true)"
    rm -f "$tmp" "$curl_err"
    die "Failed to download config from ${url}${msg:+ — $msg}"
  fi
  rm -f "$curl_err"
  RVS_CONTENT="$(<"$tmp")"
  rm -f "$tmp"
  _validate_yaml "$RVS_CONTENT" "Downloaded config"
  success "Config downloaded successfully."
}

# ---------------------------------------------------------------------------
# Path 3 — capture pasted YAML (first line already read by the caller)
# ---------------------------------------------------------------------------
_read_pasted_yaml() {
  local first_line="$1"
  echo -e "${CYAN}Reading YAML content — press ${BOLD}Ctrl-D${CYAN} on an empty line when done.${RESET}" >/dev/tty
  RVS_CONTENT="${first_line}"$'\n'
  local line
  while IFS= read -r -u 3 line; do
    RVS_CONTENT+="${line}"$'\n'
  done || true   # EOF from Ctrl-D is expected and normal
  _validate_yaml "$RVS_CONTENT" "Pasted config"
}

# ---------------------------------------------------------------------------
# Path 4 — embedded interactive setup wizard
# ---------------------------------------------------------------------------
_wizard() {
  echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════╗"
  echo        "║         RVS Setup Wizard             ║"
  echo -e     "╚══════════════════════════════════════╝${RESET}"
  echo -e "Answer the questions below to generate your RVSconfig.yml.\n"

  local domain="" subdomain="" email=""
  local cloudflare_api_token="" cloudflare_zone_id=""
  local coder_admin_password=""
  local ip_only="false" use_cloudflare="false"
  local github_token="" anthropic_api_key="" openai_api_key="" google_api_key=""
  local opencode_provider=""
  local enable_copilot="false" enable_claude="false" enable_codex="false"
  local enable_gemini="false" enable_opencode="false"

  # ── Step 1: Network / domain ──────────────────────────────────────────────
  echo -e "${BOLD}Step 1/4 — Network${RESET}"

  if _read_confirm "  Do you have a domain name for this server? [y/N]: " "n"; then
    _read_line "  Domain (e.g. example.com): "
    domain="$_TTY_LINE"

    _read_line "  Subdomain (e.g. dev): "
    subdomain="$_TTY_LINE"

    _read_line "  Email (for TLS certificates & alerts): "
    email="$_TTY_LINE"

    ip_only="false"

    if _read_confirm "  Use Cloudflare for automatic DNS? [Y/n]: " "y"; then
      use_cloudflare="true"
      echo -e "  ${CYAN}Tip: create a scoped token at https://dash.cloudflare.com/profile/api-tokens${RESET}" >/dev/tty
      _read_secret "  Cloudflare API Token: "
      cloudflare_api_token="$_TTY_SECRET"
      _read_line "  Cloudflare Zone ID: "
      cloudflare_zone_id="$_TTY_LINE"
    else
      use_cloudflare="false"
      warn "Manual DNS required: after boot, point ${subdomain:-<subdomain>}.${domain:-<domain>} → this server's public IP."
    fi
  else
    ip_only="true"
    use_cloudflare="false"
    echo -e "  ${CYAN}IP-only mode — Coder will be served over plain HTTP on port 80.${RESET}" >/dev/tty
  fi

  # ── Step 2: Admin password ────────────────────────────────────────────────
  echo -e "\n${BOLD}Step 2/4 — Coder Admin Password${RESET}"
  _read_secret "  Admin password (leave empty to auto-generate): "
  coder_admin_password="$_TTY_SECRET"
  if [[ -z "$coder_admin_password" ]]; then
    echo -e "  ${CYAN}A secure password will be auto-generated and stored in /etc/dev-server/env after boot.${RESET}" >/dev/tty
  fi

  # ── Step 3: AI agents ─────────────────────────────────────────────────────
  echo -e "\n${BOLD}Step 3/4 — AI Agents${RESET}"
  echo -e "  Select which agents to install in your Coder workspaces.\n" >/dev/tty

  if _read_confirm "  GitHub Copilot CLI? [y/N]: " "n"; then
    enable_copilot="true"
  fi
  if _read_confirm "  Claude Code (Anthropic)? [y/N]: " "n"; then
    enable_claude="true"
  fi
  if _read_confirm "  Codex CLI (OpenAI)? [y/N]: " "n"; then
    enable_codex="true"
  fi
  if _read_confirm "  Gemini CLI (Google)? [y/N]: " "n"; then
    enable_gemini="true"
  fi
  if _read_confirm "  OpenCode? [y/N]: " "n"; then
    enable_opencode="true"
  fi

  # ── Step 4: API keys ──────────────────────────────────────────────────────
  echo -e "\n${BOLD}Step 4/4 — API Keys${RESET}"

  if [[ "$enable_copilot" == "true" || "$enable_opencode" == "true" ]]; then
    echo -e "  ${CYAN}GitHub token scope needed: read:user (minimum for Copilot / OpenCode)${RESET}" >/dev/tty
    _read_secret "  GitHub Token (ghp_…): "
    github_token="$_TTY_SECRET"
  fi

  if [[ "$enable_claude" == "true" ]]; then
    _read_secret "  Anthropic API Key (sk-ant-…): "
    anthropic_api_key="$_TTY_SECRET"
  fi

  if [[ "$enable_codex" == "true" ]]; then
    _read_secret "  OpenAI API Key (sk-…): "
    openai_api_key="$_TTY_SECRET"
  fi

  if [[ "$enable_gemini" == "true" ]]; then
    _read_secret "  Google API Key: "
    google_api_key="$_TTY_SECRET"
  fi

  if [[ "$enable_opencode" == "true" ]]; then
    _read_line "  OpenCode provider [opencode-zen]: "
    opencode_provider="$_TTY_LINE"
    [[ -z "$opencode_provider" ]] && opencode_provider="opencode-zen"
  fi

  # ── Build RVSconfig.yml content ───────────────────────────────────────────
  RVS_CONTENT="# RVSconfig.yml — generated by install.sh wizard
domain: \"${domain}\"
subdomain: \"${subdomain}\"
email: \"${email}\"
cloudflare_api_token: \"${cloudflare_api_token}\"
cloudflare_zone_id: \"${cloudflare_zone_id}\"
coder_admin_password: \"${coder_admin_password}\"
ip_only: ${ip_only}
use_cloudflare: ${use_cloudflare}
enable_agent_copilot: ${enable_copilot}
enable_agent_claude: ${enable_claude}
enable_agent_codex: ${enable_codex}
enable_agent_gemini: ${enable_gemini}
enable_agent_opencode: ${enable_opencode}
github_token: \"${github_token}\"
anthropic_api_key: \"${anthropic_api_key}\"
openai_api_key: \"${openai_api_key}\"
google_api_key: \"${google_api_key}\"
opencode_provider: \"${opencode_provider}\"
"

  success "Configuration collected by wizard."
}

# ---------------------------------------------------------------------------
# 1. Resolve RVSconfig.yml
# ---------------------------------------------------------------------------
RVS_CONTENT=""
RVS_SOURCE=""

disk_path=""
if disk_path="$(_find_config_on_disk)"; then
  # ── Path 1: use existing file on disk ─────────────────────────────────────
  log "Found existing config on disk: ${disk_path} — skipping prompts."
  RVS_CONTENT="$(<"$disk_path")"
  RVS_SOURCE="disk:${disk_path}"
else
  # ── Interactive prompt (covers Paths 2, 3, 4) ─────────────────────────────
  echo -e "${BOLD}No RVSconfig.yml found on disk.${RESET}\n"
  echo -e "  ${CYAN}•${RESET} Type / paste a ${BOLD}URL${RESET} (https://…) to download your config"
  echo -e "  ${CYAN}•${RESET} ${BOLD}Paste${RESET} your RVSconfig.yml content, then press ${BOLD}Ctrl-D${RESET} on an empty line"
  echo -e "  ${CYAN}•${RESET} Press ${BOLD}Enter${RESET} (empty) to launch the interactive setup wizard"
  echo ""
  printf "> "

  _TTY_LINE=""
  IFS= read -r -u 3 _TTY_LINE || true
  first_line="$_TTY_LINE"

  if [[ -z "$first_line" ]]; then
    # ── Path 4: embedded wizard ─────────────────────────────────────────────
    _wizard
    RVS_SOURCE="wizard"
  elif [[ "$first_line" =~ ^https?:// ]]; then
    # ── Path 2: URL download ────────────────────────────────────────────────
    _download_config "$first_line"
    RVS_SOURCE="url:${first_line}"
  else
    # ── Path 3: YAML paste (first_line already contains the first row) ──────
    _read_pasted_yaml "$first_line"
    RVS_SOURCE="paste"
  fi
fi

[[ -z "$RVS_CONTENT" ]] && die "No configuration received."

log "Config resolved (source: ${RVS_SOURCE}, $(printf '%s\n' "$RVS_CONTENT" | wc -l) lines)."

# Persist to CONFIG_FILE so future re-runs use Path 1 automatically.
printf '%s\n' "$RVS_CONTENT" > "$CONFIG_FILE"
chmod 0600 "$CONFIG_FILE"
chown root:root "$CONFIG_FILE"
log "Config saved to ${CONFIG_FILE}"

# ---------------------------------------------------------------------------
# 2. Parse RVSconfig.yml → /etc/dev-server/env
# ---------------------------------------------------------------------------
# Simple parser: handles   key: "value"   key: value   key: true/false
# Skips comments and blank lines.
log "Writing environment to $ENV_FILE …"

: > "$ENV_FILE"
chmod 0600 "$ENV_FILE"
chown root:root "$ENV_FILE"

while IFS= read -r line; do
  # Strip leading/trailing whitespace
  line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  # Skip comments and blank lines
  [[ -z "$line" || "$line" == \#* ]] && continue

  # Match  key: "value"  or  key: value
  if [[ "$line" =~ ^([a-zA-Z_][a-zA-Z0-9_]*):[[:space:]]*(.*) ]]; then
    key="${BASH_REMATCH[1]}"
    val="${BASH_REMATCH[2]}"
    # Strip surrounding quotes (single or double)
    val="$(echo "$val" | sed "s/^[\"']//;s/[\"']$//")"
    # Convert key to uppercase (env convention)
    key_upper="$(echo "$key" | tr '[:lower:]' '[:upper:]')"
    # Shell-escape the value so sourcing the file is safe even if the
    # value contains spaces, quotes, $, backticks, etc.
    printf '%s=%q\n' "$key_upper" "$val" >> "$ENV_FILE"
  fi
done <<< "$RVS_CONTENT"

# Add derived CODER variables
DOMAIN="$(grep '^DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"
SUBDOMAIN="$(grep '^SUBDOMAIN=' "$ENV_FILE" | cut -d= -f2-)"
IP_ONLY_VAL="$(grep '^IP_ONLY=' "$ENV_FILE" | cut -d= -f2- || true)"
if [[ -n "$DOMAIN" && -n "$SUBDOMAIN" ]]; then
  CODER_FQDN="https://${SUBDOMAIN}.${DOMAIN}"
  grep -q '^CODER_URL=' "$ENV_FILE"        || echo "CODER_URL=${CODER_FQDN}"        >> "$ENV_FILE"
  grep -q '^CODER_ACCESS_URL=' "$ENV_FILE" || echo "CODER_ACCESS_URL=${CODER_FQDN}" >> "$ENV_FILE"
fi

log "Environment file written to $ENV_FILE"

# Quick validation — CF keys only required when a domain is configured
# and ip_only mode is not active.
if [[ "$IP_ONLY_VAL" != "true" && -n "$DOMAIN" ]]; then
  REQUIRED_KEYS=(DOMAIN SUBDOMAIN EMAIL CLOUDFLARE_API_TOKEN CLOUDFLARE_ZONE_ID)
else
  REQUIRED_KEYS=(CODER_ADMIN_PASSWORD)
fi
missing=()
for key in "${REQUIRED_KEYS[@]}"; do
  val="$(grep "^${key}=" "$ENV_FILE" | cut -d= -f2- || true)"
  if [[ -z "$val" ]]; then
    missing+=("$key")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  warn "Missing required values: ${missing[*]}"
  warn "The server may fail to provision fully."
fi

# ---------------------------------------------------------------------------
# 3. System packages + Docker
# ---------------------------------------------------------------------------
log "Installing system packages …"
apt-get update -y
apt-get install -y \
  curl wget git jq unzip apt-transport-https ca-certificates \
  gnupg lsb-release ufw fail2ban certbot

# Docker
if ! command -v docker &>/dev/null; then
  log "Installing Docker …"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
log "Docker ready."

# ---------------------------------------------------------------------------
# 4. Firewall
# ---------------------------------------------------------------------------
log "Configuring firewall …"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ---------------------------------------------------------------------------
# 5. fail2ban
# ---------------------------------------------------------------------------
systemctl enable --now fail2ban

# ---------------------------------------------------------------------------
# 6. Download provisioning scripts + bootstrap
# ---------------------------------------------------------------------------
mkdir -p "$PROVISION_DIR/infra" "$PROVISION_DIR/coder"

log "Downloading provisioning scripts …"
for f in setup.sh infra/dns.sh infra/proxy.sh infra/agents.sh coder/Dockerfile coder/devcontainer.json; do
  curl -fsSL "$REPO_URL/$f" -o "$PROVISION_DIR/$f"
  log "  ✓ $f"
done
chmod +x "$PROVISION_DIR/setup.sh" "$PROVISION_DIR/infra/"*.sh

# ---------------------------------------------------------------------------
# 7. Run setup
# ---------------------------------------------------------------------------
log "Starting setup …"
exec "$PROVISION_DIR/setup.sh"
