#!/usr/bin/env bash
# =============================================================================
# infra/dns.sh — Cloudflare DNS Automation
# =============================================================================
# Creates or updates an A record pointing $FQDN → $PUBLIC_IP via the
# Cloudflare API v4.
#
# Required environment variables (set via /etc/dev-server/env):
#   CLOUDFLARE_API_TOKEN  — scoped API token with Zone:DNS:Edit
#   CLOUDFLARE_ZONE_ID    — zone identifier for the domain
#   SUBDOMAIN             — e.g. "dev"
#   DOMAIN                — e.g. "example.com"
#   PUBLIC_IP             — server's public IPv4 address
# =============================================================================
set -euo pipefail

LOG_FILE="${LOG_FILE:-/var/log/dev-server-provision.log}"
log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [dns] $*" | tee -a "$LOG_FILE"; }
die() { log "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
: "${CLOUDFLARE_ZONE_ID:?CLOUDFLARE_ZONE_ID is required}"
: "${SUBDOMAIN:?SUBDOMAIN is required}"
: "${DOMAIN:?DOMAIN is required}"
: "${PUBLIC_IP:?PUBLIC_IP is required}"

FQDN="${SUBDOMAIN}.${DOMAIN}"
CF_API="https://api.cloudflare.com/client/v4"

# ---------------------------------------------------------------------------
# Helper — Cloudflare API call
# ---------------------------------------------------------------------------
cf_api() {
  local method="$1" endpoint="$2"
  shift 2
  curl -fsSL -X "$method" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    -H "Content-Type: application/json" \
    "$CF_API$endpoint" \
    "$@"
}

# ---------------------------------------------------------------------------
# Check for existing record
# ---------------------------------------------------------------------------
log "Looking up existing A record for $FQDN …"
EXISTING=$(cf_api GET "/zones/$CLOUDFLARE_ZONE_ID/dns_records?type=A&name=$FQDN")

RECORD_COUNT=$(echo "$EXISTING" | jq '.result | length')
log "Found $RECORD_COUNT existing A record(s)."

# ---------------------------------------------------------------------------
# Create or update
# ---------------------------------------------------------------------------
PAYLOAD=$(jq -n \
  --arg name "$FQDN" \
  --arg ip   "$PUBLIC_IP" \
  '{type:"A", name:$name, content:$ip, ttl:120, proxied:false}')

if [[ "$RECORD_COUNT" -gt 0 ]]; then
  RECORD_ID=$(echo "$EXISTING" | jq -r '.result[0].id')
  CURRENT_IP=$(echo "$EXISTING" | jq -r '.result[0].content')

  if [[ "$CURRENT_IP" == "$PUBLIC_IP" ]]; then
    log "A record already points to $PUBLIC_IP — no update needed."
  else
    log "Updating A record $RECORD_ID ($CURRENT_IP → $PUBLIC_IP) …"
    RESULT=$(cf_api PUT "/zones/$CLOUDFLARE_ZONE_ID/dns_records/$RECORD_ID" -d "$PAYLOAD")
    if echo "$RESULT" | jq -e '.success' >/dev/null 2>&1; then
      log "DNS record updated successfully."
    else
      die "Failed to update DNS record: $(echo "$RESULT" | jq -r '.errors')"
    fi
  fi
else
  log "Creating new A record for $FQDN → $PUBLIC_IP …"
  RESULT=$(cf_api POST "/zones/$CLOUDFLARE_ZONE_ID/dns_records" -d "$PAYLOAD")
  if echo "$RESULT" | jq -e '.success' >/dev/null 2>&1; then
    log "DNS record created successfully."
  else
    die "Failed to create DNS record: $(echo "$RESULT" | jq -r '.errors')"
  fi
fi

# ---------------------------------------------------------------------------
# Wait for propagation (best-effort)
# ---------------------------------------------------------------------------
log "Waiting for DNS propagation (up to 60 s) …"
for i in $(seq 1 12); do
  RESOLVED=$(dig +short "$FQDN" @1.1.1.1 2>/dev/null || true)
  if [[ "$RESOLVED" == "$PUBLIC_IP" ]]; then
    log "DNS propagated after ~$((i * 5)) s."
    exit 0
  fi
  sleep 5
done

log "WARN: DNS not yet visible via 1.1.1.1 — continuing anyway."
