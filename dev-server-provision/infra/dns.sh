#!/usr/bin/env bash
# =============================================================================
# infra/dns.sh — Cloudflare DNS Automation
# =============================================================================
# Creates or updates DNS records via the Cloudflare API v4:
#   1. A record:  $FQDN        → $PUBLIC_IP  (main Coder access)
#   2. A record:  *.$FQDN      → $PUBLIC_IP  (wildcard for Coder port forwarding)
#
# The wildcard record enables Coder's subdomain-based app/port routing so that
# any port opened inside a workspace is automatically reachable via
#   https://<port>--<workspace>--<owner>.$FQDN
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
# Helper — Ensure an A record exists and points to $PUBLIC_IP
# Usage: ensure_a_record <record_name>
# ---------------------------------------------------------------------------
ensure_a_record() {
  local record_name="$1"

  log "Looking up existing A record for $record_name …"
  local existing
  existing=$(cf_api GET "/zones/$CLOUDFLARE_ZONE_ID/dns_records?type=A&name=$record_name")

  local record_count
  record_count=$(echo "$existing" | jq '.result | length')
  log "Found $record_count existing A record(s) for $record_name."

  local payload
  payload=$(jq -n \
    --arg name "$record_name" \
    --arg ip   "$PUBLIC_IP" \
    '{type:"A", name:$name, content:$ip, ttl:120, proxied:false}')

  if [[ "$record_count" -gt 0 ]]; then
    local record_id current_ip
    record_id=$(echo "$existing" | jq -r '.result[0].id')
    current_ip=$(echo "$existing" | jq -r '.result[0].content')

    if [[ "$current_ip" == "$PUBLIC_IP" ]]; then
      log "A record $record_name already points to $PUBLIC_IP — no update needed."
    else
      log "Updating A record $record_name ($current_ip → $PUBLIC_IP) …"
      local result
      result=$(cf_api PUT "/zones/$CLOUDFLARE_ZONE_ID/dns_records/$record_id" -d "$payload")
      if echo "$result" | jq -e '.success' >/dev/null 2>&1; then
        log "DNS record $record_name updated successfully."
      else
        die "Failed to update DNS record $record_name: $(echo "$result" | jq -r '.errors')"
      fi
    fi
  else
    log "Creating new A record for $record_name → $PUBLIC_IP …"
    local result
    result=$(cf_api POST "/zones/$CLOUDFLARE_ZONE_ID/dns_records" -d "$payload")
    if echo "$result" | jq -e '.success' >/dev/null 2>&1; then
      log "DNS record $record_name created successfully."
    else
      die "Failed to create DNS record $record_name: $(echo "$result" | jq -r '.errors')"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Create / update DNS records
# ---------------------------------------------------------------------------
# 1. Main A record: dev.example.com → PUBLIC_IP
ensure_a_record "$FQDN"

# 2. Wildcard A record: *.dev.example.com → PUBLIC_IP
#    Required for Coder's subdomain-based port forwarding / app routing.
WILDCARD_FQDN="*.${FQDN}"
ensure_a_record "$WILDCARD_FQDN"

# ---------------------------------------------------------------------------
# Wait for propagation (best-effort — checks main record only)
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
