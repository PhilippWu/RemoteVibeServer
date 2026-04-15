#!/usr/bin/env bash
# =============================================================================
# infra/proxy.sh — Caddy Reverse Proxy + Automatic HTTPS (incl. Wildcard)
# =============================================================================
# Builds a custom Caddy binary with the Cloudflare DNS module and configures
# it as a reverse proxy in front of Coder.  Caddy handles automatic TLS
# certificate provisioning via Let's Encrypt:
#   • HTTP-01 challenge for the main domain ($FQDN)
#   • DNS-01 challenge via Cloudflare for the wildcard (*.$FQDN)
#
# The wildcard certificate enables Coder's subdomain-based port forwarding
# so workspace services are accessible at https://<port>--<ws>--<owner>.$FQDN.
#
# Why Caddy?
#   • Zero-config HTTPS with automatic certificate renewal
#   • Built-in reverse proxy with WebSocket support (critical for Coder)
#   • Single static binary — low attack surface
#   • Production-proven and actively maintained
#
# Required environment variables:
#   FQDN                  — fully qualified domain name (e.g. dev.example.com)
#   EMAIL                 — used for ACME account registration
#   CLOUDFLARE_API_TOKEN  — for DNS-01 wildcard TLS challenge
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
: "${FQDN:?FQDN is required}"
: "${EMAIL:?EMAIL is required}"
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required (for DNS-01 wildcard TLS)}"

# ---------------------------------------------------------------------------
# Install Caddy with Cloudflare DNS module (for wildcard TLS via DNS-01)
# ---------------------------------------------------------------------------
# Standard Caddy cannot obtain wildcard certificates because Let's Encrypt
# requires the DNS-01 ACME challenge for those.  We use xcaddy to build a
# custom Caddy binary that includes the Cloudflare DNS provider plugin.
# ---------------------------------------------------------------------------
if command -v caddy &>/dev/null && caddy list-modules 2>/dev/null | grep -q dns.providers.cloudflare; then
  log "Caddy with Cloudflare DNS module is already installed — $(caddy version)"
else
  log "Building custom Caddy with Cloudflare DNS module …"

  # Install Go (required by xcaddy) if not already present
  if ! command -v go &>/dev/null; then
    log "Installing Go (required by xcaddy) …"
    GO_VERSION="1.22.2"
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
      | tar -C /usr/local -xz
    export PATH="/usr/local/go/bin:$PATH"
  fi

  # Install xcaddy
  if ! command -v xcaddy &>/dev/null; then
    log "Installing xcaddy …"
    go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
    export PATH="$HOME/go/bin:$PATH"
  fi

  # Build Caddy with Cloudflare DNS plugin
  log "Building Caddy binary (this may take a minute) …"
  xcaddy build --with github.com/caddy-dns/cloudflare --output /usr/bin/caddy

  # If Caddy was previously installed via apt, stop the service first
  systemctl stop caddy 2>/dev/null || true

  log "Custom Caddy installed — $(caddy version)"
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

cat > "$CADDYFILE" <<EOF
# =============================================================================
# Caddyfile — maintenance mode
# Generated by RemoteVibeServer provisioning; replaced on completion.
# =============================================================================
{
    email $EMAIL
}

$FQDN, *.$FQDN {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }

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

# Ensure log directory exists with correct ownership for caddy user
mkdir -p /var/log/caddy
chown -R caddy:caddy /var/log/caddy

# ---------------------------------------------------------------------------
# Expose CLOUDFLARE_API_TOKEN to Caddy (needed for DNS-01 TLS challenge)
# ---------------------------------------------------------------------------
mkdir -p /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/cloudflare.conf <<EOF
[Service]
Environment=CLOUDFLARE_API_TOKEN=$CLOUDFLARE_API_TOKEN
EOF
systemctl daemon-reload

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
  log "Caddy is running (maintenance mode) — https://$FQDN shows provisioning page"
else
  die "Caddy failed to start — check 'journalctl -u caddy'"
fi
