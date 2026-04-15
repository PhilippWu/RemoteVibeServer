#!/usr/bin/env bash
# =============================================================================
# setup.sh — Main orchestration script for RemoteVibeServer
# =============================================================================
# Responsibilities:
#   1. Validate required environment variables
#   2. Detect the server's public IP address
#   3. Create / update DNS records  (infra/dns.sh)
#   4. Install Coder as the remote-IDE platform
#   5. Configure reverse proxy + HTTPS  (infra/proxy.sh)
#   6. Optionally install AI coding agents  (infra/agents.sh)
#   7. Write deployment artifacts & status
# =============================================================================
set -euo pipefail

# Suppress interactive prompts from apt/dpkg and needrestart during provisioning.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# cloud-init runcmd runs without a login shell — HOME is not set.
export HOME="${HOME:-/root}"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_FILE="/etc/dev-server/env"
PROVISION_DIR="/opt/dev-server-provision"
LOG_FILE="/var/log/dev-server-provision.log"
STATUS_FILE="/etc/dev-server/status"

INFRA_DIR="$PROVISION_DIR/infra"
CODER_DIR="$PROVISION_DIR/coder"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [setup] $*" | tee -a "$LOG_FILE"; }
err()  { log "ERROR: $*" >&2; }
die()  { err "$@"; exit 1; }

# ---------------------------------------------------------------------------
# Source environment (idempotent — may already be exported by bootstrap.sh)
# ---------------------------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# ---------------------------------------------------------------------------
# 1. Validate required variables
# ---------------------------------------------------------------------------
log "Validating environment …"

REQUIRED_VARS=(
  DOMAIN
  SUBDOMAIN
  EMAIL
  CLOUDFLARE_API_TOKEN
  CLOUDFLARE_ZONE_ID
)

missing=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  die "Missing required environment variables: ${missing[*]}"
fi

FQDN="${SUBDOMAIN}.${DOMAIN}"
export FQDN
log "FQDN resolved to $FQDN"

# ---------------------------------------------------------------------------
# 2. Detect public IP
# ---------------------------------------------------------------------------
log "Detecting public IP address …"
PUBLIC_IP="$(curl -fsSL https://api.ipify.org || curl -fsSL https://ifconfig.me || curl -fsSL https://icanhazip.com)"
PUBLIC_IP="$(echo "$PUBLIC_IP" | tr -d '[:space:]')"
export PUBLIC_IP
log "Public IP: $PUBLIC_IP"

# ---------------------------------------------------------------------------
# 3. DNS record creation
# ---------------------------------------------------------------------------
log "Configuring DNS …"
bash "$INFRA_DIR/dns.sh"

# ---------------------------------------------------------------------------
# 4. Install Coder
# ---------------------------------------------------------------------------
log "Installing Coder …"
install_coder() {
  if command -v coder &>/dev/null; then
    log "Coder is already installed — skipping binary install."
  else
    log "Installing Coder via official install script …"
    curl -fsSL https://coder.com/install.sh | sh -s -- --method=standalone
  fi

  # Ensure Coder data directory exists
  mkdir -p /var/lib/coder

  # Coder's built-in PostgreSQL cannot run as root — create a dedicated user
  if ! id -u coder &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir /var/lib/coder --create-home coder
    log "Created 'coder' system user"
  fi
  chown -R coder:coder /var/lib/coder

  # Allow the coder service user to manage Docker containers (required for workspace provisioning)
  usermod -aG docker coder
  log "Added 'coder' user to 'docker' group"

  # Create / update systemd unit
  cat > /etc/systemd/system/coder.service <<EOF
[Unit]
Description=Coder — Remote Development Platform
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=coder
Group=coder
EnvironmentFile=$ENV_FILE
Environment=CODER_ACCESS_URL=https://${FQDN}
Environment=CODER_WILDCARD_ACCESS_URL=*.${FQDN}
Environment=CODER_HTTP_ADDRESS=127.0.0.1:3000
Environment=CODER_TLS_ENABLE=false
ExecStart=/usr/local/bin/coder server
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now coder.service
  log "Coder service started on 127.0.0.1:3000"
}

install_coder

# ---------------------------------------------------------------------------
# 5. Reverse proxy + HTTPS
# ---------------------------------------------------------------------------
log "Configuring reverse proxy & HTTPS …"
bash "$INFRA_DIR/proxy.sh"

# ---------------------------------------------------------------------------
# 6. Optional AI agents
# ---------------------------------------------------------------------------
log "Checking AI agent flags …"
bash "$INFRA_DIR/agents.sh"

# ---------------------------------------------------------------------------
# 6b. Open development port range in UFW
# ---------------------------------------------------------------------------
# Workspace containers and Docker Compose services may expose TCP ports
# (databases, backend APIs, etc.) that need to be reachable from the
# developer's machine.  We allow a generous range so tools like MongoDB
# Compass, database GUIs, or direct API testing work without extra config.
# ---------------------------------------------------------------------------
log "Opening development port range 3000–9999 in UFW …"
if ufw status | grep -q "3000:9999/tcp"; then
  log "Port range 3000–9999/tcp already allowed in UFW."
else
  ufw allow 3000:9999/tcp
  log "UFW: allowed 3000–9999/tcp for development services."
fi

# ---------------------------------------------------------------------------
# 7. Build default Coder template image (optional, non-blocking)
# ---------------------------------------------------------------------------
if [[ -f "$CODER_DIR/Dockerfile" ]]; then
  log "Building default workspace Docker image …"
  docker build -t remotevibe-workspace:latest "$CODER_DIR" || log "WARN: Workspace image build failed (non-fatal)"
fi

# ---------------------------------------------------------------------------
# 7b. Create Coder template and first admin user (headless)
# ---------------------------------------------------------------------------
_CODER_ADMIN_PASS=""  # set by push_coder_template if admin user is created here

push_coder_template() {
  local coder_api="http://127.0.0.1:3000"

  if [[ ! -f "$CODER_DIR/main.tf" ]]; then
    log "WARN: No main.tf in $CODER_DIR — skipping template push."
    return 0
  fi

  log "Waiting for Coder API to become ready …"
  local ready=false
  for i in $(seq 1 30); do
    if curl -sf "${coder_api}/api/v2/buildinfo" >/dev/null 2>&1; then
      ready=true
      log "Coder API ready (attempt $i)."
      break
    fi
    sleep 2
  done
  if [[ "$ready" != "true" ]]; then
    log "WARN: Coder API not ready after 60s — skipping template push."
    return 0
  fi

  # Use the password from cloud-init env if set; otherwise auto-generate.
  local admin_user="admin"
  local admin_pass="${CODER_ADMIN_PASSWORD:-}"
  if [[ -z "$admin_pass" ]]; then
    admin_pass="$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 24)"
    log "CODER_ADMIN_PASSWORD not set — auto-generated a random password."
  fi

  log "Creating first Coder admin user (${EMAIL}, username: ${admin_user}) …"
  local resp_body resp_code
  resp_body="$(mktemp)"
  resp_code="$(curl -s -o "$resp_body" -w '%{http_code}' \
    -X POST "${coder_api}/api/v2/users/first" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"username\":\"${admin_user}\",\"password\":\"${admin_pass}\",\"trial\":false}" \
    2>/dev/null)" || resp_code="000"
  local first_resp; first_resp="$(cat "$resp_body")"; rm -f "$resp_body"

  if [[ "$resp_code" == "201" ]]; then
    log "Admin user created (HTTP 201)."
    _CODER_ADMIN_PASS="$admin_pass"
  elif [[ "$resp_code" == "409" ]]; then
    log "WARN: Admin user already exists (HTTP 409) — first-user was created outside of provisioning."
    log "WARN: Skipping template push. To recover, reset the admin password then push manually:"
    log "WARN:   coder reset-password admin --postgres-url 'postgresql:///coder?host=/var/lib/coder/.config/coderv2/postgres'"
    log "WARN:   CODER_URL=https://$FQDN coder templates push remotevibe --directory $CODER_DIR --yes"
    return 0
  else
    log "WARN: Admin user creation failed (HTTP ${resp_code}): ${first_resp}"
    log "WARN: Skipping template push."
    return 0
  fi

  # Obtain a session token
  local token_body token_code token
  token_body="$(mktemp)"
  token_code="$(curl -s -o "$token_body" -w '%{http_code}' \
    -X POST "${coder_api}/api/v2/users/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${admin_pass}\"}" \
    2>/dev/null)" || token_code="000"
  token="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('session_token',''))" < "$token_body" 2>/dev/null || true)"
  rm -f "$token_body"

  if [[ -z "${token:-}" ]]; then
    log "WARN: Could not obtain Coder session token (HTTP ${token_code}) — skipping template push."
    return 0
  fi

  # Create a long-lived API token so workspace agents can push template updates.
  local api_tok_body api_tok_code api_tok_key
  api_tok_body="$(mktemp)"
  api_tok_code="$(curl -s -o "$api_tok_body" -w '%{http_code}' \
    -X POST "${coder_api}/api/v2/users/me/keys/tokens" \
    -H "Coder-Session-Token: $token" \
    -H "Content-Type: application/json" \
    -d '{"token_name":"workspace-template-editor","lifetime":0,"scope":"all"}' \
    2>/dev/null)" || api_tok_code="000"
  api_tok_key="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('key',''))" < "$api_tok_body" 2>/dev/null || true)"
  rm -f "$api_tok_body"
  # Pre-create as a file so Docker bind-mount doesn't turn it into a directory.
  # 0644 so the non-root coder user inside the container can read it.
  mkdir -p /etc/dev-server
  touch /etc/dev-server/coder-admin-token
  chmod 0644 /etc/dev-server/coder-admin-token
  if [[ -n "${api_tok_key:-}" ]]; then
    echo "$api_tok_key" > /etc/dev-server/coder-admin-token
    log "Long-lived Coder admin token saved → /etc/dev-server/coder-admin-token"
  else
    log "WARN: Could not create long-lived Coder token (HTTP ${api_tok_code}) — workspace template editing requires manual 'coder login'"
  fi

  log "Pushing Coder workspace template 'remotevibe' …"
  CODER_URL="$coder_api" CODER_SESSION_TOKEN="$token" \
    coder templates push remotevibe \
      --directory "$CODER_DIR" \
      --yes \
    2>&1 | tee -a "$LOG_FILE" \
    && log "Coder template 'remotevibe' pushed successfully." \
    || log "WARN: Template push failed — push manually: CODER_URL=https://${FQDN} coder templates push remotevibe --directory ${CODER_DIR} --yes"
}

push_coder_template

# ---------------------------------------------------------------------------
# 7c. Switch Caddy from maintenance mode to live reverse proxy
# ---------------------------------------------------------------------------
enable_coder_proxy() {
  local caddyfile="/etc/caddy/Caddyfile"
  log "Enabling live Caddy reverse proxy → Coder …"

  cat > "$caddyfile" <<CADDYEOF
# =============================================================================
# Caddyfile — auto-generated by RemoteVibeServer provisioning
# =============================================================================
{
    email $EMAIL
}

# Main Coder access + wildcard subdomains for port forwarding / app routing.
# Wildcard TLS via DNS-01 challenge (Cloudflare).
$FQDN, *.$FQDN {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }

    reverse_proxy 127.0.0.1:3000

    # WebSocket support (required for Coder terminal & IDE sessions)
    @websockets {
        header Connection *Upgrade*
        header Upgrade    websocket
    }
    reverse_proxy @websockets 127.0.0.1:3000

    # Security headers
    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options    "nosniff"
        X-Frame-Options           "SAMEORIGIN"
        Referrer-Policy            "strict-origin-when-cross-origin"
        -Server
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 50MiB
            roll_keep 5
        }
    }
}
CADDYEOF

  caddy validate --config "$caddyfile" --adapter caddyfile \
    && systemctl reload caddy \
    && log "Coder is now accessible at https://$FQDN" \
    || log "WARN: Caddy config validation failed — check $caddyfile"
}

enable_coder_proxy

# ---------------------------------------------------------------------------
# 8. Write deployment status
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "$STATUS_FILE")"
cat > "$STATUS_FILE" <<STATUSEOF
provisioned_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
fqdn=$FQDN
public_ip=$PUBLIC_IP
coder_url=https://$FQDN
coder_status=$(systemctl is-active coder.service 2>/dev/null || echo "unknown")
caddy_status=$(systemctl is-active caddy.service 2>/dev/null || echo "unknown")
STATUSEOF

if [[ -n "${_CODER_ADMIN_PASS:-}" ]]; then
  {
    echo "coder_admin_user=admin"
    echo "coder_admin_email=${EMAIL}"
    echo "coder_admin_password=${_CODER_ADMIN_PASS}"
  } >> "$STATUS_FILE"
  log "Admin credentials written to $STATUS_FILE"
fi
chmod 0600 "$STATUS_FILE"

log "============================================"
log " Provisioning complete!"
log " Coder URL : https://$FQDN"
log " Status    : $STATUS_FILE"
if [[ -n "${_CODER_ADMIN_PASS:-}" ]]; then
  log " Admin     : ${EMAIL}  /  password in status file"
fi
log " Log       : $LOG_FILE"
log "============================================"
