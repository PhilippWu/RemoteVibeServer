"""Parse existing cloud-init.yaml or RVSconfig.yml files to pre-fill the configurator.

Both formats are produced by the RemoteVibeServer Configurator itself, so the
parsing is intentionally straightforward and handles older variants via a
two-stage approach:

1. Structured extraction  — knows the exact layout of the generated files.
2. Regex/line fallback    — catches hand-edited or slightly different versions.

No external dependencies (PyYAML is not required).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Key mappings
# ---------------------------------------------------------------------------

# Config dict keys that hold boolean agent-enable flags.
_BOOL_KEYS: frozenset[str] = frozenset({
    "enable_agent_copilot",
    "enable_agent_claude",
    "enable_agent_gemini",
    "enable_agent_codex",
    "enable_agent_opencode",
})

# Shell env-var name → config dict key.
_ENV_VAR_TO_KEY: dict[str, str] = {
    "DOMAIN": "domain",
    "SUBDOMAIN": "subdomain",
    "EMAIL": "email",
    "CLOUDFLARE_API_TOKEN": "cloudflare_api_token",
    "CLOUDFLARE_ZONE_ID": "cloudflare_zone_id",
    "CODER_ADMIN_PASSWORD": "coder_admin_password",
    "ENABLE_AGENT_COPILOT": "enable_agent_copilot",
    "ENABLE_AGENT_CLAUDE": "enable_agent_claude",
    "ENABLE_AGENT_GEMINI": "enable_agent_gemini",
    "ENABLE_AGENT_CODEX": "enable_agent_codex",
    "ENABLE_AGENT_OPENCODE": "enable_agent_opencode",
    "OPENAI_API_KEY": "openai_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "GITHUB_TOKEN": "github_token",
    "CODEX_OPENAI_AUTH_CODE": "codex_openai_auth_code",
    "OPENCODE_PROVIDER": "opencode_provider",
}

# All known config keys (used to whitelist RVSconfig.yml keys).
_KNOWN_KEYS: frozenset[str] = frozenset(_ENV_VAR_TO_KEY.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _str_to_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _parse_env_block(text: str) -> dict[str, Any]:
    """Parse a ``KEY=value`` style block into a config dict.

    Comment lines (``#``) and blank lines are ignored.  Only keys present in
    ``_ENV_VAR_TO_KEY`` are extracted.
    """
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        env_key, _, value = line.partition("=")
        env_key = env_key.strip()
        value = value.strip()
        config_key = _ENV_VAR_TO_KEY.get(env_key)
        if config_key is None:
            continue
        result[config_key] = _str_to_bool(value) if config_key in _BOOL_KEYS else value
    return result


def _extract_env_block_from_cloud_init(text: str) -> str | None:
    """Return the raw content of the ``/etc/dev-server/env`` write_files entry.

    Handles both YAML literal-block style (generated files) and edge cases
    where the block might be slightly differently indented.
    """
    # Find the path marker, then scan forward for "content: |"
    path_match = re.search(r"path:\s*/etc/dev-server/env\b", text)
    if not path_match:
        return None

    after_path = text[path_match.end():]

    # Find content: | or content: |-
    content_match = re.search(r"content:\s*\|[-]?\s*\n", after_path)
    if not content_match:
        return None

    block_start = content_match.end()
    block_text = after_path[block_start:]

    # Determine indentation of the first non-empty line
    first_line_match = re.match(r"( +)\S", block_text)
    if not first_line_match:
        return None

    indent = first_line_match.group(1)
    indent_len = len(indent)

    # Collect lines that belong to this indented block
    lines: list[str] = []
    for line in block_text.splitlines():
        if line == "" or line.startswith(indent):
            lines.append(line[indent_len:])  # strip the leading indent
        else:
            break  # end of block

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------

def parse_cloud_init(path: str | Path) -> dict[str, Any]:
    """Extract config values from a ``cloud-init.yaml`` file.

    Finds the ``/etc/dev-server/env`` content block and parses its
    ``KEY=value`` pairs.  Returns an empty dict if extraction fails.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    env_block = _extract_env_block_from_cloud_init(text)
    if env_block:
        return _parse_env_block(env_block)
    return {}


def parse_rvs_config(path: str | Path) -> dict[str, Any]:
    """Extract config values from an ``RVSconfig.yml`` file.

    The file uses simple ``key: "value"`` / ``key: true`` YAML scalars as
    produced by :func:`generator.generate_rvs_config`.  Handles:
    - Double-quoted strings (with ``\\``, ``\\"`` and ``\\n`` escapes)
    - Unquoted ``true`` / ``false`` booleans
    - Unquoted plain strings
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r'^(\w+):\s*(.*)$', line)
        if not m:
            continue

        key, raw_value = m.group(1), m.group(2).strip()
        if key not in _KNOWN_KEYS:
            continue

        # Unquoted boolean
        if raw_value in ("true", "false"):
            value: Any = raw_value == "true"
        # Double-quoted string
        elif len(raw_value) >= 2 and raw_value[0] == '"' and raw_value[-1] == '"':
            inner = raw_value[1:-1]
            inner = inner.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n')
            value = inner
        # Empty or unquoted string
        else:
            value = raw_value

        if key in _BOOL_KEYS and not isinstance(value, bool):
            value = _str_to_bool(str(value))

        result[key] = value

    return result


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_config_files(search_dir: str | Path | None = None) -> list[Path]:
    """Return existing config files in *search_dir* (default: ``cwd``).

    Scans for:
    - ``cloud-init.yaml`` / ``cloud-init.yml``
    - ``cloud-init*.yaml`` glob (e.g. ``cloud-init.old.yaml``)
    - ``RVSconfig.yml`` / ``rvsconfig.yml``

    Results are sorted newest-first by modification time.
    """
    base = Path(search_dir) if search_dir else Path.cwd()
    seen: set[Path] = set()
    candidates: list[Path] = []

    # Explicit names first (keeps order predictable)
    for name in ("cloud-init.yaml", "cloud-init.yml", "RVSconfig.yml", "rvsconfig.yml"):
        p = base / name
        if p.is_file() and p not in seen:
            candidates.append(p)
            seen.add(p)

    # Glob for any additional cloud-init*.yaml variants
    for p in sorted(base.glob("cloud-init*.yaml")) + sorted(base.glob("cloud-init*.yml")):
        if p.is_file() and p not in seen:
            candidates.append(p)
            seen.add(p)

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Detect the file type and parse it.

    Dispatches to :func:`parse_cloud_init` or :func:`parse_rvs_config` based
    on the file name.  If neither parser produces results the other is tried
    as a fallback.  Returns an empty dict on any error.
    """
    p = Path(path)
    name_lower = p.name.lower()

    try:
        if "cloud-init" in name_lower or name_lower.endswith((".yaml", ".yml")):
            # Check first line for #cloud-config marker
            first_line = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            if "#cloud-config" in first_line:
                result = parse_cloud_init(p)
                return result if result else parse_rvs_config(p)

        if "rvsconfig" in name_lower:
            result = parse_rvs_config(p)
            return result if result else parse_cloud_init(p)

        # Unknown: try cloud-init first, then RVSconfig
        result = parse_cloud_init(p)
        return result if result else parse_rvs_config(p)

    except Exception:
        return {}
