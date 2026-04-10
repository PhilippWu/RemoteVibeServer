"""OAuth helpers for obtaining AI-provider tokens from the configurator CLI.

Supported flows
---------------
* **GitHub Device Flow** – ideal for CLI tools; the user visits a URL and
  enters a short code while the CLI polls for the resulting access token.
* **Authorization-code exchange** – the user pastes a callback URL (or bare
  code) and the CLI exchanges it for an access token via the provider's
  token endpoint.

All HTTP interaction uses the stdlib :mod:`urllib` so that no extra
dependencies are required.
"""

from __future__ import annotations

import json
import os
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class DeviceCodeResponse:
    """Parsed response from the GitHub device-code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int
    verification_uri_complete: str = ""


@dataclass
class OpenAIDeviceCodeResponse:
    """Parsed response from the OpenAI device-code endpoint.

    OpenAI's endpoint returns a ``device_auth_id`` (instead of
    ``device_code``) and a ``user_code``.  The verification URL is
    always ``https://auth.openai.com/codex/device``.
    """

    device_auth_id: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int = 900  # 15 minutes


@dataclass
class OAuthToken:
    """Minimal wrapper around an OAuth access token."""

    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class OAuthError(Exception):
    """Raised when an OAuth flow fails."""


class OAuthHTTPError(OAuthError):
    """Raised when an OAuth HTTP request returns a non-success status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Built-in OAuth Client IDs / Secrets per provider
# ---------------------------------------------------------------------------
# Each AI-agent provider that supports OAuth has a built-in Client ID (and
# optionally a Client Secret) so the CLI can run a Device Flow or
# Authorization-Code Flow out-of-the-box — no manual setup needed.
#
# **How to register your own OAuth app for each provider:**
#
# GitHub (Copilot / Codex CLI / OpenCode)
#   1. https://github.com/settings/applications/new
#   2. Check "Enable Device Flow"
#   3. No callback URL required — pure Device Flow
#   4. Scope: ``read:user``
#   → Paste Client ID below or set GITHUB_OAUTH_CLIENT_ID env var.
#
# Google (Gemini CLI)
#   1. https://console.cloud.google.com/apis/credentials
#   2. Create an "OAuth 2.0 Client ID" (type: Desktop App or Web)
#   3. Enable the Generative Language API
#   4. For CLI use, choose "Desktop App" (uses authorization-code flow
#      with redirect to ``http://localhost``)
#   5. Scope: ``https://www.googleapis.com/auth/generative-language``
#   → Paste Client ID + Client Secret below or set env vars.
#
# Anthropic (Claude Code)
#   Anthropic does **not** offer OAuth.  Authentication is via a plain
#   API key (``ANTHROPIC_API_KEY``).  No Client ID is needed — the
#   configurator prompts the user for the key directly.
#
# OpenAI (Codex CLI)
#   Codex CLI supports two authentication modes:
#   a) **GitHub Device Flow** — reuses the same GitHub OAuth App as
#      Copilot / OpenCode.  The CLI calls ``/login/device/code`` and
#      the user approves in a browser.
#   b) **OpenAI API Key** — a plain ``OPENAI_API_KEY`` passed via env.
#   No separate OpenAI OAuth registration is needed.
#
# OpenCode (multi-provider)
#   OpenCode supports multiple upstream providers.  From the provider
#   selection screen it offers: OpenCode Zen (recommended), OpenCode Go,
#   OpenAI, GitHub Copilot, Anthropic, and Google.
#   Authentication uses the GitHub Device Flow **or** provider API keys
#   (OpenAI, Anthropic, Google).  No separate OAuth registration needed.
#
# Override any value at runtime via the corresponding environment
# variable (highest priority).
# ---------------------------------------------------------------------------

# -- GitHub (Copilot, Codex CLI & OpenCode) --------------------------------
_GITHUB_OAUTH_CLIENT_ID = "Ov23liu7cPhVnaUoWhUl"

# -- Google (Gemini CLI) ---------------------------------------------------
# Register at https://console.cloud.google.com/apis/credentials
_GOOGLE_OAUTH_CLIENT_ID = ""
_GOOGLE_OAUTH_CLIENT_SECRET = ""

# -- Anthropic (Claude Code) -----------------------------------------------
# No OAuth — uses plain API key.  Placeholder for consistency.
_ANTHROPIC_OAUTH_CLIENT_ID = ""

# -- OpenAI (Codex CLI) ----------------------------------------------------
# Codex CLI supports three authentication modes:
#   a) **OpenAI Device Flow** — the user visits auth.openai.com/codex/device
#      and enters a short code (ChatGPT Plus/Pro plan, no API billing).
#      Built-in Client ID: app_EMoamEEZ73f0CkXaXp7hrann
#      Override via OPENAI_CODEX_CLIENT_ID env var.
#   b) **GitHub Device Flow** — reuses the same GitHub OAuth App as
#      Copilot / OpenCode.
#   c) **OpenAI API Key** — a plain OPENAI_API_KEY passed via env.
_OPENAI_OAUTH_CLIENT_ID = ""


def get_github_client_id() -> str:
    """Return the GitHub OAuth Client ID to use for the Device Flow.

    Resolution order:
    1. ``GITHUB_OAUTH_CLIENT_ID`` environment variable (highest priority)
    2. Built-in ``_GITHUB_OAUTH_CLIENT_ID`` constant
    """
    return os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip() or _GITHUB_OAUTH_CLIENT_ID


def get_google_client_id() -> str:
    """Return the Google OAuth Client ID for the Gemini authorization-code flow.

    Resolution order:
    1. ``GOOGLE_OAUTH_CLIENT_ID`` environment variable
    """
    return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip() or _GOOGLE_OAUTH_CLIENT_ID


def get_google_client_secret() -> str:
    """Return the Google OAuth Client Secret for the Gemini authorization-code flow.

    Resolution order:
    1. ``GOOGLE_OAUTH_CLIENT_SECRET`` environment variable
    """
    return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip() or _GOOGLE_OAUTH_CLIENT_SECRET


def get_anthropic_client_id() -> str:
    """Return the Anthropic OAuth Client ID (placeholder — Anthropic uses API keys).

    Provided for interface consistency.  Currently always returns ``""``.

    Resolution order:
    1. ``ANTHROPIC_OAUTH_CLIENT_ID`` environment variable
    2. Built-in ``_ANTHROPIC_OAUTH_CLIENT_ID`` constant
    """
    return os.environ.get("ANTHROPIC_OAUTH_CLIENT_ID", "").strip() or _ANTHROPIC_OAUTH_CLIENT_ID


def get_openai_client_id() -> str:
    """Return the OpenAI OAuth Client ID (placeholder — Codex CLI uses GitHub OAuth or API key).

    Provided for interface consistency.  Currently always returns ``""``.

    Resolution order:
    1. ``OPENAI_OAUTH_CLIENT_ID`` environment variable
    2. Built-in ``_OPENAI_OAUTH_CLIENT_ID`` constant
    """
    return os.environ.get("OPENAI_OAUTH_CLIENT_ID", "").strip() or _OPENAI_OAUTH_CLIENT_ID


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post_form(url: str, data: dict[str, str], accept: str = "application/json") -> dict[str, Any]:
    """POST form-encoded *data* to *url* and return the JSON response."""
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Accept": accept, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise OAuthError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"Network error reaching {url}: {exc.reason}") from exc

    # GitHub may return form-encoded or JSON depending on Accept header.
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type:
        return json.loads(body)
    # Fallback: try JSON first, then form-encoded
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return dict(urllib.parse.parse_qsl(body))


# ---------------------------------------------------------------------------
# GitHub Device Flow
# ---------------------------------------------------------------------------

_GH_DEVICE_CODE_URL = "https://github.com/login/device/code"
_GH_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GH_DEFAULT_SCOPE = "read:user"


# ---------------------------------------------------------------------------
# OpenAI Device Flow (Codex CLI — ChatGPT Plus/Pro plan)
# ---------------------------------------------------------------------------
# Codex CLI uses OpenAI's own OAuth Device Flow for users with a ChatGPT
# Plus, Pro, Team, or Enterprise subscription.  The endpoints live under
# ``https://auth.openai.com`` and are separate from the GitHub Device Flow.
#
# Source: openai/codex repository — codex-rs/login/src/auth/manager.rs
#         and codex-rs/login/src/device_code_auth.rs

_OPENAI_AUTH_ISSUER = "https://auth.openai.com"
_OPENAI_DEVICE_CODE_URL = f"{_OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/usercode"
_OPENAI_DEVICE_TOKEN_URL = f"{_OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/token"
_OPENAI_DEVICE_VERIFY_URL = f"{_OPENAI_AUTH_ISSUER}/codex/device"
_OPENAI_DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


# ---------------------------------------------------------------------------
# Google OAuth endpoints (Gemini)
# ---------------------------------------------------------------------------

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_DEFAULT_SCOPE = "https://www.googleapis.com/auth/generative-language"


def request_github_device_code(client_id: str, scope: str = _GH_DEFAULT_SCOPE) -> DeviceCodeResponse:
    """Request a device code from GitHub.

    Returns a :class:`DeviceCodeResponse` that the caller can display to
    the user.

    Raises :class:`OAuthError` on network or API errors.
    """
    data = {"client_id": client_id, "scope": scope}
    resp = _post_form(_GH_DEVICE_CODE_URL, data)

    if "error" in resp:
        raise OAuthError(resp.get("error_description", resp["error"]))

    return DeviceCodeResponse(
        device_code=resp["device_code"],
        user_code=resp["user_code"],
        verification_uri=resp.get("verification_uri", "https://github.com/login/device"),
        interval=int(resp.get("interval", 5)),
        expires_in=int(resp.get("expires_in", 900)),
        verification_uri_complete=resp.get("verification_uri_complete", ""),
    )


def poll_github_access_token(
    client_id: str,
    device_code: str,
    interval: int = 5,
    expires_in: int = 900,
) -> OAuthToken:
    """Poll GitHub until the user completes authorization or the code expires.

    This blocks (sleeping *interval* seconds between attempts) and returns
    an :class:`OAuthToken` on success.

    Raises :class:`OAuthError` if the code expires, is denied, or a
    network error occurs.
    """
    deadline = time.monotonic() + expires_in

    while time.monotonic() < deadline:
        time.sleep(interval)

        data = {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }

        resp = _post_form(_GH_ACCESS_TOKEN_URL, data)

        error = resp.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = int(resp.get("interval", interval + 5))
            continue
        if error == "expired_token":
            raise OAuthError("Device code expired — please restart the flow.")
        if error == "access_denied":
            raise OAuthError("Authorization was denied by the user.")
        if error:
            raise OAuthError(resp.get("error_description", error))

        access_token = resp.get("access_token", "")
        if access_token:
            return OAuthToken(
                access_token=access_token,
                token_type=resp.get("token_type", "bearer"),
                scope=resp.get("scope", ""),
            )

    raise OAuthError("Timed out waiting for authorization.")


def github_device_flow(client_id: str, scope: str = _GH_DEFAULT_SCOPE) -> OAuthToken:
    """Run the full GitHub Device Flow end-to-end.

    1. Request a device code.
    2. Poll until the user authorizes (or the code expires).
    3. Return the resulting :class:`OAuthToken`.
    """
    dc = request_github_device_code(client_id, scope)
    return poll_github_access_token(
        client_id=client_id,
        device_code=dc.device_code,
        interval=dc.interval,
        expires_in=dc.expires_in,
    )


# ---------------------------------------------------------------------------
# OpenAI Device Flow (Codex CLI — ChatGPT account)
# ---------------------------------------------------------------------------

def _post_json(url: str, data: dict[str, str], accept: str = "application/json") -> dict[str, Any]:
    """POST JSON-encoded *data* to *url* and return the JSON response.

    The request includes ``User-Agent`` and ``originator`` headers that
    match the real Codex CLI (``codex_cli_rs``).  Without these,
    Cloudflare's bot-protection on ``auth.openai.com`` rejects the
    request with HTTP 530.
    """
    system = platform.system()
    release = platform.release()
    machine = platform.machine() or "unknown"
    ua = f"codex_cli_rs/0.0.0-configurator ({system} {release}; {machine})"

    encoded = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Accept": accept,
            "Content-Type": "application/json",
            "User-Agent": ua,
            "originator": "codex_cli_rs",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise OAuthHTTPError(f"HTTP {exc.code} from {url}", status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"Network error reaching {url}: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body.strip().replace("\n", " ").replace("\r", " ")
        if not preview:
            preview = "<empty response>"
        elif len(preview) > 200:
            preview = f"{preview[:200]}..."
        raise OAuthError(f"Invalid JSON response from {url}: {preview}") from exc


def get_openai_codex_client_id() -> str:
    """Return the OpenAI Codex CLI Client ID for the Device Flow.

    Resolution order:
    1. ``OPENAI_CODEX_CLIENT_ID`` environment variable (highest priority)
    2. Built-in ``_OPENAI_DEFAULT_CLIENT_ID`` constant
    """
    return os.environ.get("OPENAI_CODEX_CLIENT_ID", "").strip() or _OPENAI_DEFAULT_CLIENT_ID


def request_openai_device_code(client_id: str = "") -> OpenAIDeviceCodeResponse:
    """Request a device code from OpenAI for Codex CLI.

    Returns an :class:`OpenAIDeviceCodeResponse` that the caller can display.

    Raises :class:`OAuthError` on network or API errors.
    """
    if not client_id:
        client_id = get_openai_codex_client_id()

    resp = _post_json(_OPENAI_DEVICE_CODE_URL, {"client_id": client_id})

    if "error" in resp:
        raise OAuthError(resp.get("error_description", resp["error"]))

    return OpenAIDeviceCodeResponse(
        device_auth_id=resp["device_auth_id"],
        # OpenAI's API may return "user_code" or "usercode" depending on
        # the server version (the Rust Codex CLI also handles both via
        # #[serde(alias = "user_code", alias = "usercode")] in its struct).
        user_code=resp.get("user_code", resp.get("usercode", "")),
        verification_uri=_OPENAI_DEVICE_VERIFY_URL,
        interval=int(resp.get("interval", 5)),
    )


def poll_openai_device_token(
    device_auth_id: str,
    user_code: str,
    interval: int = 5,
    expires_in: int = 900,
) -> OAuthToken:
    """Poll OpenAI until the user completes device authorization or the code expires.

    This blocks (sleeping *interval* seconds between attempts) and returns
    an :class:`OAuthToken` on success.  The returned token contains the
    ``authorization_code`` which Codex CLI then exchanges via PKCE — but
    for our configurator we treat it as the access credential to store.

    Raises :class:`OAuthError` if the code expires or a network error occurs.
    """
    deadline = time.monotonic() + expires_in

    while time.monotonic() < deadline:
        time.sleep(interval)

        try:
            resp = _post_json(
                _OPENAI_DEVICE_TOKEN_URL,
                {"device_auth_id": device_auth_id, "user_code": user_code},
            )
        except OAuthHTTPError as exc:
            # HTTP 403 / 404 means "authorization_pending" in OpenAI's flow
            # (the user hasn't approved yet). Any other status is a real error.
            if exc.status_code in (403, 404):
                continue
            raise
        except OAuthError:
            raise

        # Success — the response contains authorization_code + PKCE values
        auth_code = resp.get("authorization_code", "")
        if auth_code:
            return OAuthToken(
                access_token=auth_code,
                token_type="authorization_code",
                scope="codex",
            )

    raise OAuthError("Timed out waiting for OpenAI device authorization (15 min).")


# ---------------------------------------------------------------------------
# Callback URL / authorization-code helpers
# ---------------------------------------------------------------------------

def extract_code_from_callback_url(callback_url: str) -> str:
    """Extract the ``code`` query parameter from an OAuth callback URL.

    Accepts a full URL (``https://…?code=XYZ``) **or** a bare
    authorization code string.

    Raises :class:`OAuthError` if the URL contains an ``error`` parameter.
    """
    callback_url = callback_url.strip()
    if not callback_url:
        raise OAuthError("Empty callback URL or code.")

    # Bare code (no scheme) — return as-is
    if "://" not in callback_url and "?" not in callback_url:
        return callback_url

    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)

    if "error" in params:
        desc = params.get("error_description", params["error"])
        if isinstance(desc, list):
            desc = desc[0]
        raise OAuthError(f"OAuth error in callback: {desc}")

    codes = params.get("code")
    if codes:
        return codes[0]

    raise OAuthError(
        "No 'code' parameter found in the callback URL.  "
        "Please paste the full callback URL or just the authorization code."
    )


def exchange_authorization_code(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = "",
) -> OAuthToken:
    """Exchange an authorization *code* for an access token.

    This is a generic helper that works with any OAuth 2.0 provider
    supporting the standard authorization-code grant.

    Raises :class:`OAuthError` on failure.
    """
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    resp = _post_form(token_url, data)

    if "error" in resp:
        raise OAuthError(resp.get("error_description", resp["error"]))

    access_token = resp.get("access_token", "")
    if not access_token:
        raise OAuthError("No access_token in response from token endpoint.")

    return OAuthToken(
        access_token=access_token,
        token_type=resp.get("token_type", "bearer"),
        scope=resp.get("scope", ""),
    )


def build_authorization_url(
    authorize_url: str,
    client_id: str,
    redirect_uri: str = "",
    scope: str = "",
    state: str = "",
) -> str:
    """Build an OAuth 2.0 authorization URL the user should visit.

    Returns the full URL with query parameters.
    """
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    if scope:
        params["scope"] = scope
    if state:
        params["state"] = state

    parsed_url = urllib.parse.urlparse(authorize_url)
    merged_params = dict(
        urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
    )
    merged_params.update(params)

    return urllib.parse.urlunparse(
        parsed_url._replace(query=urllib.parse.urlencode(merged_params))
    )


# ---------------------------------------------------------------------------
# Google (Gemini) authorization-code flow helpers
# ---------------------------------------------------------------------------

def build_google_authorization_url(
    redirect_uri: str = "http://localhost:8085",
    scope: str = _GOOGLE_DEFAULT_SCOPE,
    state: str = "",
) -> str:
    """Build the Google OAuth authorization URL for the Gemini CLI.

    Uses the environment-provided Google Client ID.
    Returns the full URL the user should open in a browser.

    Raises :class:`OAuthError` if no Client ID is configured.
    """
    client_id = get_google_client_id()
    if not client_id:
        raise OAuthError(
            "No Google OAuth Client ID configured. "
            "Set GOOGLE_OAUTH_CLIENT_ID."
        )
    return build_authorization_url(
        authorize_url=_GOOGLE_AUTHORIZE_URL,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
    )


def exchange_google_authorization_code(
    code: str,
    redirect_uri: str = "http://localhost:8085",
) -> OAuthToken:
    """Exchange a Google authorization code for an access token.

    Uses the environment-provided Google Client ID / Secret.

    Raises :class:`OAuthError` on failure or if credentials are missing.
    """
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    if not client_id or not client_secret:
        raise OAuthError(
            "Google OAuth Client ID and Secret are required. "
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )
    return exchange_authorization_code(
        token_url=_GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )
