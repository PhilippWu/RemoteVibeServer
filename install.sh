#!/usr/bin/env bash
# =============================================================================
# install.sh — RemoteVibeServer bare-server installer
# =============================================================================
# One-liner usage:
#   curl -fsSL https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/install.sh | sudo bash
#
# The script:
#   1. Prompts the operator to paste the contents of RVSconfig.yml
#   2. Parses the YAML into /etc/dev-server/env
#   3. Installs Docker, configures ufw + fail2ban
#   4. Downloads and executes the bootstrap → setup pipeline
#
# Designed for a fresh Ubuntu 22.04 / 24.04 server.
# Must be run as root.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_FILE="/etc/dev-server/env"
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

die() { echo -e "${RED}ERROR: $*${RESET}" >&2; exit 1; }

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
# 1. Read RVSconfig.yml from stdin / paste
# ---------------------------------------------------------------------------
# When the script is piped (curl ... | sudo bash), stdin is the curl stream.
# We read interactive input from /dev/tty so the user can still paste config.
echo -e "${BOLD}Paste the contents of your RVSconfig.yml below.${RESET}"
echo -e "When done, press ${BOLD}Ctrl-D${RESET} (EOF) on an empty line.\n"

RVS_CONTENT=""
while IFS= read -r line <&3; do
  RVS_CONTENT+="$line"$'\n'
done 3< /dev/tty

if [[ -z "$RVS_CONTENT" ]]; then
  die "No configuration received.  Please paste your RVSconfig.yml content."
fi

log "RVSconfig.yml received ($(echo "$RVS_CONTENT" | wc -l) lines)."

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
if [[ -n "$DOMAIN" && -n "$SUBDOMAIN" ]]; then
  CODER_FQDN="https://${SUBDOMAIN}.${DOMAIN}"
  grep -q '^CODER_URL=' "$ENV_FILE" || echo "CODER_URL=${CODER_FQDN}" >> "$ENV_FILE"
  grep -q '^CODER_ACCESS_URL=' "$ENV_FILE" || echo "CODER_ACCESS_URL=${CODER_FQDN}" >> "$ENV_FILE"
fi

log "Environment file written to $ENV_FILE"

# Quick validation
REQUIRED_KEYS=(DOMAIN SUBDOMAIN EMAIL CLOUDFLARE_API_TOKEN CLOUDFLARE_ZONE_ID)
missing=()
for key in "${REQUIRED_KEYS[@]}"; do
  val="$(grep "^${key}=" "$ENV_FILE" | cut -d= -f2- || true)"
  if [[ -z "$val" ]]; then
    missing+=("$key")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo -e "${YELLOW}⚠  Missing required values: ${missing[*]}${RESET}"
  echo -e "${YELLOW}   The server may fail to provision fully.${RESET}"
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
