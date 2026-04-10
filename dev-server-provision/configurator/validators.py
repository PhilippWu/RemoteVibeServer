"""Input validation and preflight checks for RemoteVibeServer configurator."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


# ---------------------------------------------------------------------------
# Individual field validators
# ---------------------------------------------------------------------------

def validate_domain(value: str) -> str | bool:
    """Return True if ``value`` looks like a valid domain, else an error string."""
    value = value.strip()
    if not value:
        return "Domain is required."
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    if not re.match(pattern, value):
        return "Invalid domain format (e.g. example.com)."
    return True


def validate_subdomain(value: str) -> str | bool:
    """Return True if ``value`` is a valid subdomain label."""
    value = value.strip()
    if not value:
        return "Subdomain is required."
    pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    if not re.match(pattern, value):
        return "Invalid subdomain (letters, digits, hyphens; 1-63 chars)."
    return True


def validate_email(value: str) -> str | bool:
    """Basic email format check."""
    value = value.strip()
    if not value:
        return "Email is required."
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(pattern, value):
        return "Invalid email format."
    return True


def validate_cloudflare_api_token(value: str) -> str | bool:
    """Validate a Cloudflare scoped API token (minimum 20 characters)."""
    value = value.strip()
    if not value:
        return "Cloudflare API token is required."
    if len(value) < 20:
        return "Token seems too short — expected a scoped Cloudflare API token."
    return True


def validate_cloudflare_zone_id(value: str) -> str | bool:
    """Zone IDs are 32-char hex strings."""
    value = value.strip()
    if not value:
        return "Cloudflare Zone ID is required."
    if not re.match(r"^[a-fA-F0-9]{32}$", value):
        return "Zone ID should be a 32-character hex string."
    return True



def validate_coder_password(value: str) -> str | bool:
    """Validate a Coder admin password.

    Coder enforces minimum 8 characters and no whitespace.
    """
    value = value.strip()
    if not value:
        return "Password is required."
    if len(value) < 8:
        return "Password must be at least 8 characters (Coder requirement)."
    if any(ch.isspace() for ch in value):
        return "Password must not contain spaces."
    return True



    """Accept empty or any non-whitespace string."""
    return True


def validate_api_key_nonempty(value: str) -> str | bool:
    """Require at least one character."""
    if not value.strip():
        return "This API key is required for the selected agent."
    return True


def validate_oauth_client_id(value: str) -> str | bool:
    """Validate an OAuth client ID (non-empty, printable, no whitespace)."""
    value = value.strip()
    if not value:
        return "OAuth Client ID is required."
    if any(ch.isspace() for ch in value):
        return "Client ID must not contain whitespace."
    if not value.isprintable():
        return "Client ID must contain only printable characters."
    return True


def validate_callback_url_or_code(value: str) -> str | bool:
    """Accept a full OAuth callback URL **or** a bare authorization code."""
    value = value.strip()
    if not value:
        return "Please paste the callback URL or authorization code."
    return True


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

class PreflightResult:
    """Container for a single preflight check outcome."""

    def __init__(self, name: str, passed: bool, message: str) -> None:
        self.name = name
        self.passed = passed
        self.message = message

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


def _check_required_fields(config: dict[str, Any]) -> PreflightResult:
    """All required fields must be non-empty."""
    required = ["domain", "subdomain", "email", "cloudflare_api_token", "cloudflare_zone_id", "coder_admin_password"]
    missing = [f for f in required if not config.get(f)]
    if missing:
        return PreflightResult("Required fields", False, f"Missing: {', '.join(missing)}")
    return PreflightResult("Required fields", True, "All required fields provided.")


def _check_agent_keys(config: dict[str, Any]) -> PreflightResult:
    """Enabled agents must have their corresponding API keys."""
    issues: list[str] = []

    if config.get("enable_agent_copilot") and not config.get("github_token"):
        issues.append("Copilot enabled but GITHUB_TOKEN is empty")
    if config.get("enable_agent_claude") and not config.get("anthropic_api_key"):
        issues.append("Claude enabled but ANTHROPIC_API_KEY is empty")
    if config.get("enable_agent_gemini") and not config.get("google_api_key"):
        issues.append("Gemini enabled but GOOGLE_API_KEY is empty")
    if config.get("enable_agent_codex"):
        has_key = config.get("github_token") or config.get("openai_api_key") or config.get("codex_openai_auth_code")
        if not has_key:
            issues.append("Codex enabled but neither GITHUB_TOKEN, OPENAI_API_KEY, nor CODEX_OPENAI_AUTH_CODE is set")
    if config.get("enable_agent_opencode"):
        provider_str = config.get("opencode_provider", "")
        # Support comma-separated multi-provider strings
        provider_list = [p.strip() for p in provider_str.split(",") if p.strip()] if provider_str else []
        for provider in provider_list:
            if provider in ("opencode-zen", "opencode-go", "github-copilot"):
                if not config.get("github_token"):
                    issues.append(f"OpenCode ({provider}) enabled but GITHUB_TOKEN is empty")
            elif provider == "openai":
                if not config.get("openai_api_key"):
                    issues.append("OpenCode (openai) enabled but OPENAI_API_KEY is empty")
            elif provider == "anthropic":
                if not config.get("anthropic_api_key"):
                    issues.append("OpenCode (anthropic) enabled but ANTHROPIC_API_KEY is empty")
            elif provider == "google":
                if not config.get("google_api_key"):
                    issues.append("OpenCode (google) enabled but GOOGLE_API_KEY is empty")
            else:
                issues.append(f"OpenCode provider '{provider}' is not supported")
        if not provider_list:
            # Fallback: at least one key must be present
            has_key = any(config.get(k) for k in ("openai_api_key", "anthropic_api_key", "google_api_key", "github_token"))
            if not has_key:
                issues.append("OpenCode enabled but no provider API key set")

    if issues:
        return PreflightResult("Agent API keys", False, "; ".join(issues))
    return PreflightResult("Agent API keys", True, "All enabled agents have required keys.")


def _check_hcloud_cli() -> PreflightResult:
    """Check whether the Hetzner Cloud CLI is available locally."""
    if shutil.which("hcloud"):
        try:
            result = subprocess.run(
                ["hcloud", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip() or "unknown"
                return PreflightResult("hcloud CLI", True, f"Found ({version}).")
            error = result.stderr.strip() or f"`hcloud version` exited with status {result.returncode}."
            return PreflightResult("hcloud CLI", False, f"Installed but failed to run: {error}")
        except subprocess.TimeoutExpired as exc:
            error = (exc.stderr or "").strip() or "Timed out while running `hcloud version`."
            return PreflightResult("hcloud CLI", False, f"Installed but failed to run: {error}")
        except OSError as exc:
            return PreflightResult("hcloud CLI", False, f"Installed but failed to run: {exc}")
    return PreflightResult("hcloud CLI", False, "Not found — install it to deploy directly.")


def run_preflight_checks(config: dict[str, Any], *, provider: str = "hetzner") -> list[PreflightResult]:
    """Execute all preflight checks and return the results."""
    results: list[PreflightResult] = [
        _check_required_fields(config),
        _check_agent_keys(config),
    ]
    if provider == "hetzner":
        results.append(_check_hcloud_cli())
    return results
