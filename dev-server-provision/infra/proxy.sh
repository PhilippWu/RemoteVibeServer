#!/usr/bin/env bash
# =============================================================================
# infra/proxy.sh — Caddy Reverse Proxy + Automatic HTTPS
# =============================================================================
# Installs Caddy and configures it as a reverse proxy in front of Coder.
# Caddy handles automatic TLS certificate provisioning via Let's Encrypt
# (ACME HTTP-01), so no manual certbot step is needed.
#
# Why Caddy?
#   • Zero-config HTTPS with automatic certificate renewal
#   • Built-in reverse proxy with WebSocket support (critical for Coder)
#   • Single static binary — low attack surface
#   • Production-proven and actively maintained
#
# Required environment variables:
#   FQDN   — fully qualified domain name (e.g. dev.example.com)
#   EMAIL  — used for ACME account registration
# =============================================================================
set -euo pipefail

# Suppress interactive prompts from apt/dpkg and needrestart during provisioning.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# Prevent apt/dpkg interactive prompts (needrestart, debconf, etc.)
export DEBIAN_FRONTEND=noninteractive

LOG_FILE="${LOG_FILE:-/var/log/dev-server-provision.log}"
log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [proxy] $*" | tee -a "$LOG_FILE"; }
die() { log "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
# In IP-only mode FQDN equals the public IP and EMAIL may be empty.
# For a domain-based deployment both are required (Caddy needs them for ACME).
if [[ "${IP_ONLY:-false}" != "true" ]]; then
  : "${FQDN:?FQDN is required}"
  : "${EMAIL:?EMAIL is required}"
fi

# ---------------------------------------------------------------------------
# Install Caddy (idempotent)
# ---------------------------------------------------------------------------
if command -v caddy &>/dev/null; then
  log "Caddy is already installed — $(caddy version)"
else
  log "Installing Caddy …"
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
  log "Caddy installed — $(caddy version)"
fi

# ---------------------------------------------------------------------------
# Write maintenance page (shown while Coder is being provisioned)
# ---------------------------------------------------------------------------
MAINTENANCE_DIR="/etc/caddy/maintenance"
CADDYFILE="/etc/caddy/Caddyfile"

mkdir -p "$MAINTENANCE_DIR"
log "Writing maintenance page → $MAINTENANCE_DIR/index.html"

cat > "$MAINTENANCE_DIR/index.html" <<'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="30">
  <title>RemoteVibeServer &mdash; Provisioning in Progress</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f111a;
      color: #cdd6f4;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .box {
      max-width: 560px;
      width: 90%;
      padding: 2.5rem;
      border: 1px solid #313244;
      border-radius: 12px;
      background: #181825;
      text-align: center;
    }
    h1 { font-size: 1.6rem; margin-bottom: 0.5rem; color: #89b4fa; }
    .spinner {
      display: inline-block;
      width: 2.5rem;
      height: 2.5rem;
      border: 3px solid #313244;
      border-top-color: #89b4fa;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 1.5rem auto;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    p { line-height: 1.6; color: #a6adc8; margin: 0.5rem 0; }
    code {
      background: #313244;
      padding: 0.15em 0.45em;
      border-radius: 4px;
      font-family: monospace;
      font-size: 0.9em;
      color: #cba6f7;
    }
    .note {
      margin-top: 1.5rem;
      font-size: 0.875rem;
      border-top: 1px solid #313244;
      padding-top: 1.25rem;
    }
  </style>
</head>
<body>
  <div class="box">
    <h1>&#x1F680; RemoteVibeServer</h1>
    <div class="spinner"></div>
    <p><strong>Provisioning in progress&hellip;</strong></p>
    <p>Coder and workspace templates are being installed.<br>
       This typically takes 5&ndash;10&nbsp;minutes.</p>
    <p style="margin-top:1rem">
      This page refreshes automatically every 30&nbsp;seconds.<br>
      When setup is complete, the Coder&nbsp;login page will appear.
    </p>
    <div class="note">
      <p>Your login credentials will be stored on the server:</p>
      <p style="margin-top:0.5rem">
        <code>ssh root@&lt;server-ip&gt; cat /etc/dev-server/status</code>
      </p>
    </div>
  </div>
</body>
</html>
HTMLEOF

# ---------------------------------------------------------------------------
# Write maintenance-mode Caddyfile (static file server — no proxy to Coder yet)
# setup.sh will replace this with the live reverse-proxy config when done.
# ---------------------------------------------------------------------------
log "Writing maintenance Caddyfile → $CADDYFILE"

if [[ "${IP_ONLY:-false}" == "true" ]]; then
  # IP-only: plain HTTP on port 80 — no TLS, no ACME, no domain needed.
  cat > "$CADDYFILE" <<EOF
# =============================================================================
# Caddyfile — IP-only mode (plain HTTP)
# Generated by RemoteVibeServer provisioning; replaced on completion.
# =============================================================================

http://${PUBLIC_IP} {
    root * $MAINTENANCE_DIR
    file_server

    header {
        Cache-Control "no-cache, no-store, must-revalidate"
        -Server
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 50MiB
            roll_keep 5
        }
    }
}
EOF
else
  cat > "$CADDYFILE" <<EOF
# =============================================================================
# Caddyfile — maintenance mode
# Generated by RemoteVibeServer provisioning; replaced on completion.
# =============================================================================
{
    email $EMAIL
}

$FQDN {
    root * $MAINTENANCE_DIR
    file_server

    header {
        Cache-Control "no-cache, no-store, must-revalidate"
        -Server
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 50MiB
            roll_keep 5
        }
    }
}
EOF
fi

# Ensure log directory exists with correct ownership for caddy user
mkdir -p /var/log/caddy
chown -R caddy:caddy /var/log/caddy

# ---------------------------------------------------------------------------
# Validate & start
# ---------------------------------------------------------------------------
log "Validating Caddy configuration …"
caddy validate --config "$CADDYFILE" --adapter caddyfile || die "Caddyfile validation failed"

# Re-apply ownership after validate (which may create access.log as root)
chown -R caddy:caddy /var/log/caddy

log "Enabling and starting Caddy (maintenance mode) …"
systemctl enable caddy
systemctl restart caddy

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
sleep 3
if systemctl is-active --quiet caddy; then
  if [[ "${IP_ONLY:-false}" == "true" ]]; then
    log "Caddy is running (maintenance mode) — http://${PUBLIC_IP} shows provisioning page"
  else
    log "Caddy is running (maintenance mode) — https://$FQDN shows provisioning page"
  fi
else
  die "Caddy failed to start — check 'journalctl -u caddy'"
fi
