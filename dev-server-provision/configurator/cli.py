"""Interactive CLI flow for the RemoteVibeServer configurator."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from typing import Any

from InquirerPy import inquirer

from . import generator, importer, oauth, providers, validators

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def _clickable_url(url: str, label: str | None = None) -> str:
    """Return an OSC 8 terminal hyperlink so *url* is clickable in the CLI.

    Modern terminal emulators (iTerm2, GNOME Terminal ≥ 3.26, Windows
    Terminal, etc.) render OSC 8 sequences as clickable links.  Terminals
    that do not support the escape simply show the *label* text as-is.
    """
    display = label if label else url
    return f"\033]8;;{url}\033\\{display}\033]8;;\033\\"


def _banner() -> None:
    print(
        f"""
{_CYAN}╔══════════════════════════════════════════════════════════════╗
║          RemoteVibeServer — Init-Script Configurator         ║
╚══════════════════════════════════════════════════════════════╝{_RESET}
"""
    )


def _heading(title: str) -> None:
    print(f"\n{_BOLD}── {title} ──{_RESET}\n")


def _success(msg: str) -> None:
    print(f"{_GREEN}✔ {msg}{_RESET}")


def _warn(msg: str) -> None:
    print(f"{_YELLOW}⚠ {msg}{_RESET}")


def _error(msg: str) -> None:
    print(f"{_RED}✖ {msg}{_RESET}")


# ---------------------------------------------------------------------------
# Device-flow recovery actions
# ---------------------------------------------------------------------------

_RECOVER_RETRY = "retry"
_RECOVER_MANUAL = "manual"
_RECOVER_SKIP = "skip"


def _ask_device_flow_recovery(provider_label: str) -> str:
    """Prompt the user after a Device Flow failure.

    Returns one of ``_RECOVER_RETRY``, ``_RECOVER_MANUAL``, or
    ``_RECOVER_SKIP`` so the caller can retry the flow, fall back to
    manual key entry, or skip entirely without aborting the configurator.
    """
    return inquirer.select(
        message=f"{provider_label} Device Flow failed — what would you like to do?",
        choices=[
            {"name": "Retry the Device Flow", "value": _RECOVER_RETRY},
            {"name": "Enter token / API key manually", "value": _RECOVER_MANUAL},
            {"name": "Skip (configure later)", "value": _RECOVER_SKIP},
        ],
        default=_RECOVER_RETRY,
    ).execute()


# ---------------------------------------------------------------------------
# Step 1 — Cloud provider selection
# ---------------------------------------------------------------------------

def _ask_provider() -> providers.Provider:
    _heading("Cloud Provider")
    provider_id = inquirer.select(
        message="Select your cloud provider:",
        choices=providers.provider_choices(),
        default="hetzner",
    ).execute()
    return providers.get_provider(provider_id)


# ---------------------------------------------------------------------------
# Step 0 — Import from existing config file (optional)
# ---------------------------------------------------------------------------

_IMPORT_SKIP = "__skip__"


def _ask_import(config: dict[str, Any]) -> None:
    """Offer to pre-fill the wizard from an existing cloud-init.yaml / RVSconfig.yml.

    Scans the current working directory for known config files and, if any are
    found, asks the user which one to import.  Parsed values are merged into
    *config* so that subsequent steps can use them as defaults.
    """
    found = importer.find_config_files()
    if not found:
        return

    _heading("Import Previous Configuration")
    print(f"  Found {len(found)} existing config file(s) in the current directory.")
    print(f"  You can pre-fill this wizard from one of them.\n")

    choices = [{"name": f.name, "value": str(f)} for f in found]
    choices.append({"name": "Don't import — start fresh", "value": _IMPORT_SKIP})

    selected = inquirer.select(
        message="Import values from:",
        choices=choices,
        default=str(found[0]),
    ).execute()

    if selected == _IMPORT_SKIP:
        return

    imported = importer.load_config_file(selected)
    if not imported:
        _warn(f"Could not read any values from '{selected}'. Starting fresh.")
        return

    # Merge: only set keys that are in the default config schema and not empty
    for key, value in imported.items():
        if key in config:
            config[key] = value

    key_count = len(imported)
    _success(f"Imported {key_count} value(s) from '{selected}'. "
             "You can review and change them in each step below.")


# ---------------------------------------------------------------------------
# Step 2 — Domain & DNS
# ---------------------------------------------------------------------------

def _ask_domain_config(config: dict[str, Any]) -> None:
    _heading("Domain & DNS")

    config["domain"] = inquirer.text(
        message="Root domain (e.g. example.com):",
        default=config.get("domain") or "",
        validate=validators.validate_domain,
        invalid_message="",
    ).execute().strip()

    config["subdomain"] = inquirer.text(
        message="Subdomain (e.g. dev):",
        default=config.get("subdomain") or "dev",
        validate=validators.validate_subdomain,
        invalid_message="",
    ).execute().strip()

    config["email"] = inquirer.text(
        message="Email (for Let's Encrypt & alerts):",
        default=config.get("email") or "",
        validate=validators.validate_email,
        invalid_message="",
    ).execute().strip()


# ---------------------------------------------------------------------------
# Step 3 — Cloudflare
# ---------------------------------------------------------------------------

def _ask_cloudflare_config(config: dict[str, Any]) -> None:
    _heading("Cloudflare DNS")

    config["cloudflare_api_token"] = inquirer.secret(
        message="Cloudflare API Token (Zone:DNS:Edit):",
        default=config.get("cloudflare_api_token") or "",
        validate=validators.validate_cloudflare_api_token,
        invalid_message="",
    ).execute().strip()

    config["cloudflare_zone_id"] = inquirer.text(
        message="Cloudflare Zone ID (32-char hex):",
        default=config.get("cloudflare_zone_id") or "",
        validate=validators.validate_cloudflare_zone_id,
        invalid_message="",
    ).execute().strip()


# ---------------------------------------------------------------------------
# Step 4 — AI agents
# ---------------------------------------------------------------------------

_AGENT_CHOICES = [
    {"name": "GitHub Copilot CLI", "value": "copilot"},
    {"name": "Anthropic Claude Code", "value": "claude"},
    {"name": "Google Gemini CLI", "value": "gemini"},
    {"name": "OpenAI Codex CLI", "value": "codex"},
    {"name": "OpenCode AI (multi-provider)", "value": "opencode"},
]

_OPENCODE_PROVIDER_CHOICES = [
    {"name": "OpenCode Zen (Recommended)", "value": "opencode-zen"},
    {"name": "OpenCode Go — Low cost subscription for everyone", "value": "opencode-go"},
    {"name": "OpenAI (ChatGPT Plus/Pro or API key)", "value": "openai"},
    {"name": "GitHub Copilot", "value": "github-copilot"},
    {"name": "Anthropic (API key)", "value": "anthropic"},
    {"name": "Google", "value": "google"},
]


def _ask_github_token_oauth(config: dict[str, Any]) -> None:
    """Obtain a GitHub token via the Device Flow.

    Uses the built-in or environment-provided Client ID so the user never
    needs to supply one manually — just like ``gh auth login`` or Claude
    Code.

    On failure the user is offered to **retry**, enter the token
    **manually**, or **skip** (configure later) — so the configurator
    never crashes.
    """
    client_id = oauth.get_github_client_id()

    if not client_id:
        _error("No GitHub OAuth Client ID configured.")
        print(
            f"\n  The OAuth Device Flow requires a registered GitHub OAuth App.\n"
            f"  Set the {_BOLD}GITHUB_OAUTH_CLIENT_ID{_RESET} environment variable, or\n"
            f"  register an app at {_CYAN}https://github.com/settings/applications/new{_RESET}\n"
            f'  (enable "Device Flow") and update the built-in constant.\n'
        )
        _warn("Falling back to manual token entry.")
        config["github_token"] = inquirer.secret(
            message="GitHub Token (for Copilot):",
            validate=validators.validate_api_key_nonempty,
            invalid_message="",
        ).execute().strip()
        return

    while True:
        # -- request device code ------------------------------------------
        try:
            dc = oauth.request_github_device_code(client_id)
        except oauth.OAuthError as exc:
            _error(f"Failed to start GitHub Device Flow: {exc}")
            action = _ask_device_flow_recovery("GitHub")
            if action == _RECOVER_RETRY:
                continue
            if action == _RECOVER_MANUAL:
                config["github_token"] = inquirer.secret(
                    message="GitHub Token (for Copilot):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()
            else:  # skip
                _warn("Skipping GitHub token — you can configure it later.")
            return

        # -- display code & open browser ----------------------------------
        open_url = dc.verification_uri_complete or dc.verification_uri
        link = _clickable_url(open_url)
        print(f"\n  1. Open this URL in your browser:\n")
        print(f"     {_CYAN}{link}{_RESET}")
        print(f"     {open_url}\n")
        if not dc.verification_uri_complete:
            print(f"  2. Enter code: {_BOLD}{dc.user_code}{_RESET}\n")
        else:
            print(f"     (Code {_BOLD}{dc.user_code}{_RESET} is pre-filled in the link)\n")

        browser_opened = False
        try:
            browser_opened = webbrowser.open(open_url)
        except Exception:
            pass

        if not browser_opened:
            print(f"  {_YELLOW}Could not open a browser automatically.{_RESET}")
            print(f"  {_YELLOW}Please copy the URL above and open it in your browser.{_RESET}\n")

        print("  Waiting for authorization …")

        # -- poll for token -----------------------------------------------
        try:
            token = oauth.poll_github_access_token(
                client_id=client_id,
                device_code=dc.device_code,
                interval=dc.interval,
                expires_in=dc.expires_in,
            )
            config["github_token"] = token.access_token
            _success("GitHub token obtained successfully.")
            return
        except oauth.OAuthError as exc:
            _error(f"GitHub OAuth failed: {exc}")
            action = _ask_device_flow_recovery("GitHub")
            if action == _RECOVER_RETRY:
                continue
            if action == _RECOVER_MANUAL:
                config["github_token"] = inquirer.secret(
                    message="GitHub Token (for Copilot):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()
            else:  # skip
                _warn("Skipping GitHub token — you can configure it later.")
            return


_AUTH_METHOD_MANUAL = "manual"
_AUTH_METHOD_OAUTH = "oauth"
_AUTH_METHOD_OPENAI_OAUTH = "openai_oauth"


def _ask_codex_openai_oauth(config: dict[str, Any]) -> None:
    """Obtain a Codex CLI token via the OpenAI Device Flow (ChatGPT plan).

    Uses the built-in OpenAI Codex Client ID so the user just opens a URL
    and enters a code — similar to ``codex login --device-auth``.

    On failure the user can **retry**, enter an API key **manually**, or
    **skip** without aborting the configurator.
    """
    while True:
        # -- request device code ------------------------------------------
        try:
            dc = oauth.request_openai_device_code()
        except oauth.OAuthError as exc:
            _error(f"Failed to start OpenAI Device Flow: {exc}")
            action = _ask_device_flow_recovery("OpenAI")
            if action == _RECOVER_RETRY:
                continue
            if action == _RECOVER_MANUAL:
                config["openai_api_key"] = inquirer.secret(
                    message="OpenAI API Key (for Codex CLI):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()
            else:  # skip
                _warn("Skipping OpenAI authentication — you can configure it later.")
            return

        # -- display code & open browser ----------------------------------
        link = _clickable_url(dc.verification_uri)
        print(f"\n  1. Open this URL in your browser and sign in with your ChatGPT account:\n")
        print(f"     {_CYAN}{link}{_RESET}")
        print(f"     {dc.verification_uri}\n")
        print(f"  2. Enter code: {_BOLD}{dc.user_code}{_RESET}\n")

        browser_opened = False
        try:
            browser_opened = webbrowser.open(dc.verification_uri)
        except Exception:
            pass

        if not browser_opened:
            print(f"  {_YELLOW}Could not open a browser automatically.{_RESET}")
            print(f"  {_YELLOW}Please copy the URL above and open it in your browser.{_RESET}\n")

        print("  Waiting for authorization …")

        # -- poll for token -----------------------------------------------
        try:
            token = oauth.poll_openai_device_token(
                device_auth_id=dc.device_auth_id,
                user_code=dc.user_code,
                interval=dc.interval,
                expires_in=dc.expires_in,
            )
            config["codex_openai_auth_code"] = token.access_token
            _success("OpenAI authorization obtained successfully.")
            return
        except oauth.OAuthError as exc:
            _error(f"OpenAI OAuth failed: {exc}")
            action = _ask_device_flow_recovery("OpenAI")
            if action == _RECOVER_RETRY:
                continue
            if action == _RECOVER_MANUAL:
                config["openai_api_key"] = inquirer.secret(
                    message="OpenAI API Key (for Codex CLI):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()
            else:  # skip
                _warn("Skipping OpenAI authentication — you can configure it later.")
            return



def _ask_agents(config: dict[str, Any]) -> None:
    _heading("AI Coding Agents (optional)")

    # Pre-select agents that were imported / previously enabled
    preselected = [
        agent for agent, key in [
            ("copilot", "enable_agent_copilot"),
            ("claude", "enable_agent_claude"),
            ("gemini", "enable_agent_gemini"),
            ("codex", "enable_agent_codex"),
            ("opencode", "enable_agent_opencode"),
        ] if config.get(key)
    ]

    selected = inquirer.checkbox(
        message="Enable AI agents (Space to toggle, Enter to confirm):",
        choices=_AGENT_CHOICES,
        default=preselected,
    ).execute()

    config["enable_agent_copilot"] = "copilot" in selected
    config["enable_agent_claude"] = "claude" in selected
    config["enable_agent_gemini"] = "gemini" in selected
    config["enable_agent_codex"] = "codex" in selected
    config["enable_agent_opencode"] = "opencode" in selected

    # Ask for required API keys based on selection
    if config["enable_agent_copilot"]:
        if config.get("github_token"):
            _success("Reusing GitHub token already obtained.")
        else:
            auth_method = inquirer.select(
                message="How would you like to provide the GitHub token?",
                choices=[
                    {"name": "Login via GitHub OAuth (Device Flow)", "value": _AUTH_METHOD_OAUTH},
                    {"name": "Enter token manually", "value": _AUTH_METHOD_MANUAL},
                ],
                default=_AUTH_METHOD_OAUTH,
            ).execute()

            if auth_method == _AUTH_METHOD_OAUTH:
                _ask_github_token_oauth(config)
            else:
                config["github_token"] = inquirer.secret(
                    message="GitHub Token (for Copilot):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()

    if config["enable_agent_claude"]:
        if config.get("anthropic_api_key"):
            _success("Reusing Anthropic API key already imported.")
        else:
            config["anthropic_api_key"] = inquirer.secret(
                message="Anthropic API Key (for Claude):",
                validate=validators.validate_api_key_nonempty,
                invalid_message="",
            ).execute().strip()

    if config["enable_agent_gemini"]:
        if config.get("google_api_key"):
            _success("Reusing Google API key already imported.")
        else:
            config["google_api_key"] = inquirer.secret(
                message="Google API Key (for Gemini):",
                validate=validators.validate_api_key_nonempty,
                invalid_message="",
            ).execute().strip()

    if config["enable_agent_codex"]:
        codex_auth = inquirer.select(
            message="How would you like to authenticate Codex CLI?",
            choices=[
                {"name": "Sign in with ChatGPT (Plus/Pro plan — OpenAI Device Flow)", "value": _AUTH_METHOD_OPENAI_OAUTH},
                {"name": "Login via GitHub OAuth (Device Flow)", "value": _AUTH_METHOD_OAUTH},
                {"name": "Enter OpenAI API key manually", "value": _AUTH_METHOD_MANUAL},
            ],
            default=_AUTH_METHOD_OPENAI_OAUTH,
        ).execute()

        if codex_auth == _AUTH_METHOD_OPENAI_OAUTH:
            _ask_codex_openai_oauth(config)
        elif codex_auth == _AUTH_METHOD_OAUTH:
            # Codex CLI uses the same GitHub Device Flow as Copilot
            if not config.get("github_token"):
                _ask_github_token_oauth(config)
            else:
                _success("Reusing GitHub token already obtained.")
        else:
            if not config.get("openai_api_key"):
                config["openai_api_key"] = inquirer.secret(
                    message="OpenAI API Key (for Codex CLI):",
                    validate=validators.validate_api_key_nonempty,
                    invalid_message="",
                ).execute().strip()
            else:
                _success("Reusing OpenAI API key already provided.")

    if config["enable_agent_opencode"]:
        # Pre-select providers from an imported / previously stored value
        imported_providers = [
            p.strip()
            for p in config.get("opencode_provider", "").split(",")
            if p.strip()
        ]

        # Let the user choose one or more OpenCode providers
        selected_providers: list[str] = inquirer.checkbox(
            message="Select OpenCode providers (Space to toggle, Enter to confirm):",
            choices=_OPENCODE_PROVIDER_CHOICES,
            default=imported_providers if imported_providers else None,
        ).execute()

        if not selected_providers:
            _warn("No OpenCode provider selected — defaulting to opencode-zen.")
            selected_providers = ["opencode-zen"]

        # Store as comma-separated string for the env file
        config["opencode_provider"] = ",".join(selected_providers)

        # Collect credentials for each selected provider (reusing already-obtained tokens)
        for provider in selected_providers:
            if provider in ("opencode-zen", "opencode-go"):
                # OpenCode Zen / Go use GitHub OAuth or their own auth
                if not config.get("github_token"):
                    want_oauth = inquirer.select(
                        message=f"OpenCode {provider} — authenticate via GitHub?",
                        choices=[
                            {"name": "Login via GitHub OAuth (Device Flow)", "value": _AUTH_METHOD_OAUTH},
                            {"name": "Skip (will configure later)", "value": _AUTH_METHOD_MANUAL},
                        ],
                        default=_AUTH_METHOD_OAUTH,
                    ).execute()
                    if want_oauth == _AUTH_METHOD_OAUTH:
                        _ask_github_token_oauth(config)
                else:
                    _success(f"Reusing GitHub token already obtained for {provider}.")

            elif provider == "openai":
                if not config.get("openai_api_key"):
                    config["openai_api_key"] = inquirer.secret(
                        message="OpenAI API Key (for OpenCode):",
                        validate=validators.validate_api_key_nonempty,
                        invalid_message="",
                    ).execute().strip()
                else:
                    _success("Reusing OpenAI API key already provided.")

            elif provider == "github-copilot":
                if not config.get("github_token"):
                    _ask_github_token_oauth(config)
                else:
                    _success("Reusing GitHub token already obtained.")

            elif provider == "anthropic":
                if not config.get("anthropic_api_key"):
                    config["anthropic_api_key"] = inquirer.secret(
                        message="Anthropic API Key (for OpenCode):",
                        validate=validators.validate_api_key_nonempty,
                        invalid_message="",
                    ).execute().strip()
                else:
                    _success("Reusing Anthropic API key already provided.")

            elif provider == "google":
                if not config.get("google_api_key"):
                    config["google_api_key"] = inquirer.secret(
                        message="Google API Key (for OpenCode):",
                        validate=validators.validate_api_key_nonempty,
                        invalid_message="",
                    ).execute().strip()
                else:
                    _success("Reusing Google API key already provided.")


# ---------------------------------------------------------------------------
# Step 4b — Starter app template
# ---------------------------------------------------------------------------

_STARTER_TEMPLATE_CHOICES = [
    {
        "name": "none — plain workspace (no pre-installed app)",
        "value": "none",
    },
    {
        "name": "fullstack-baseline — FastAPI + PostgreSQL + React/Vite (tiangolo/full-stack-fastapi-template)",
        "value": "fullstack-baseline",
    },
]


def _ask_starter_template(config: dict[str, Any]) -> None:
    _heading("Starter App Template (optional)")
    print(
        "  Optionally pre-install a starter application into every new workspace.\n"
        f"\n"
        f"  {_BOLD}fullstack-baseline{_RESET} bootstraps "
        f"{_CYAN}tiangolo/full-stack-fastapi-template{_RESET}:\n"
        f"    • FastAPI backend  (Python, SQLModel, Alembic migrations)\n"
        f"    • PostgreSQL database\n"
        f"    • React + Vite frontend\n"
        f"    • JWT auth + RBAC + CRUD scaffolding\n"
        f"    • Docker Compose stack (ready in ~2 min)\n"
        f"\n"
        f"  The stack starts automatically on first workspace launch and is\n"
        f"  available at http://localhost:5173 (frontend) and :8000 (API).\n"
    )

    current = config.get("starter_template") or "none"
    config["starter_template"] = inquirer.select(
        message="Starter template:",
        choices=_STARTER_TEMPLATE_CHOICES,
        default=current,
    ).execute()

    if config["starter_template"] == "fullstack-baseline":
        _success("fullstack-baseline selected — stack will auto-start on first workspace launch.")
    else:
        _success("No starter template — plain workspace.")


# ---------------------------------------------------------------------------
# Step 4 — Coder admin password
# ---------------------------------------------------------------------------

def _ask_coder_admin_password(config: dict[str, Any]) -> None:
    _heading("Coder Admin Password")
    print(
        "  Set the password you will use to log into Coder after provisioning.\n"
        f"  {_BOLD}Login email{_RESET}: the address entered above.  "
        f"{_BOLD}Username{_RESET}: admin\n"
        f"  {_YELLOW}Coder requires ≥ 8 characters, no spaces.{_RESET}\n"
    )
    config["coder_admin_password"] = inquirer.secret(
        message="Admin password (min 8 chars):",
        validate=validators.validate_coder_password,
        invalid_message="",
    ).execute().strip()
    _success("Admin password configured.")


# ---------------------------------------------------------------------------
# Step 5 — Provider-specific options (Hetzner)
# ---------------------------------------------------------------------------

def _ask_provider_options(provider: providers.Provider, deploy_config: dict[str, Any]) -> None:
    _heading(f"{provider.name} Options")

    if provider.server_types:
        choices = [{"name": st.label, "value": st.name} for st in provider.server_types]
        default = provider.server_types[1].name if len(provider.server_types) > 1 else provider.server_types[0].name
        deploy_config["server_type"] = inquirer.select(
            message="Server type:",
            choices=choices,
            default=default,
        ).execute()

    if provider.locations:
        deploy_config["location"] = inquirer.select(
            message="Server location:",
            choices=provider.locations,
            default=provider.locations[0],
        ).execute()

    deploy_config["server_name"] = inquirer.text(
        message="Server name:",
        default="dev-server",
    ).execute().strip()

    if provider.id == "hetzner":
        deploy_config["ssh_key"] = inquirer.text(
            message="SSH key name in Hetzner (leave empty to skip):",
            default="",
        ).execute().strip()


# ---------------------------------------------------------------------------
# Step 6 — Preflight checks
# ---------------------------------------------------------------------------

def _run_preflight(config: dict[str, Any], provider: providers.Provider) -> bool:
    _heading("Preflight Checks")
    results = validators.run_preflight_checks(config, provider=provider.id)
    all_passed = True
    for r in results:
        if r.passed:
            _success(f"{r.name}: {r.message}")
        else:
            _error(f"{r.name}: {r.message}")
            all_passed = False
    return all_passed


# ---------------------------------------------------------------------------
# Step 7 — Generate & save
# ---------------------------------------------------------------------------

def _generate_and_save(config: dict[str, Any]) -> str:
    _heading("Output")

    output_file = inquirer.text(
        message="Output file path:",
        default="cloud-init.yaml",
    ).execute().strip()

    yaml_content = generator.generate_cloud_init(config)

    # Safety check — refuse to overwrite without confirmation
    if os.path.exists(output_file):
        overwrite = inquirer.confirm(
            message=f"'{output_file}' already exists. Overwrite?",
            default=False,
        ).execute()
        if not overwrite:
            _warn("Aborted — file not written.")
            return ""

    # Write with restricted permissions on POSIX (file contains secrets)
    _write_secret_file(output_file, yaml_content)
    _success(f"cloud-init configuration written to: {output_file}")

    # Also write RVSconfig.yml for use with install.sh on bare servers
    rvs_content = generator.generate_rvs_config(config)
    rvs_file = "RVSconfig.yml"

    write_rvs = inquirer.confirm(
        message=f"Also write '{rvs_file}' (for bare-server install.sh)?",
        default=True,
    ).execute()

    if write_rvs:
        if os.path.exists(rvs_file):
            overwrite_rvs = inquirer.confirm(
                message=f"'{rvs_file}' already exists. Overwrite?",
                default=False,
            ).execute()
            if not overwrite_rvs:
                _warn(f"{rvs_file} not written.")
            else:
                _write_secret_file(rvs_file, rvs_content)
                _success(f"RVSconfig.yml written to: {rvs_file}")
        else:
            _write_secret_file(rvs_file, rvs_content)
            _success(f"RVSconfig.yml written to: {rvs_file}")

    return output_file


def _write_secret_file(path: str, content: str) -> None:
    """Write *content* to *path* with 0600 permissions on POSIX."""
    if os.name == "posix":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


# ---------------------------------------------------------------------------
# Step 8 — Optional Hetzner deployment
# ---------------------------------------------------------------------------

def _offer_deploy(provider: providers.Provider, deploy_config: dict[str, Any], output_file: str) -> None:
    if not output_file:
        return

    deploy_config["output_file"] = output_file
    cmd = provider.deployment_command(deploy_config)

    _heading("Deployment Command")
    print(f"{_CYAN}{cmd}{_RESET}\n")

    if provider.id == "hetzner" and shutil.which("hcloud"):
        execute = inquirer.confirm(
            message="Execute this command now?",
            default=False,
        ).execute()
        if execute:
            _heading("Deploying via hcloud …")
            argv = provider.deployment_argv(deploy_config)
            if argv is None:
                _error("No executable command available for this provider.")
                return
            try:
                subprocess.run(argv, check=True)
                _success("Server creation initiated!")
            except subprocess.CalledProcessError as exc:
                _error(f"hcloud command failed (exit code {exc.returncode}).")
            except FileNotFoundError:
                _error("hcloud CLI not found in PATH.")
    elif provider.deploy_hint:
        print(f"  ℹ  {provider.deploy_hint}\n")


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def run() -> None:
    """Run the full interactive configurator flow."""
    _banner()

    config = generator.default_config()
    deploy_config: dict[str, Any] = {}

    try:
        # 0. Import from existing config (optional pre-fill)
        _ask_import(config)

        # 1. Provider
        provider = _ask_provider()

        # 2. Domain & DNS
        _ask_domain_config(config)

        # 3. Cloudflare
        _ask_cloudflare_config(config)

        # 4. Coder admin password
        _ask_coder_admin_password(config)

        # 5. AI agents
        _ask_agents(config)

        # 5b. Starter app template
        _ask_starter_template(config)

        # 6. Provider options
        _ask_provider_options(provider, deploy_config)

        # 7. Preflight checks
        checks_ok = _run_preflight(config, provider)
        if not checks_ok:
            proceed = inquirer.confirm(
                message="Some preflight checks failed. Continue anyway?",
                default=False,
            ).execute()
            if not proceed:
                _warn("Aborted by user.")
                sys.exit(1)

        # 8. Generate & save
        output_file = _generate_and_save(config)

        # 9. Deployment
        _offer_deploy(provider, deploy_config, output_file)

        _heading("Done")
        fqdn = f"{config['subdomain']}.{config['domain']}"
        print(f"  After provisioning (~5 min), access Coder at: {_CYAN}https://{fqdn}{_RESET}")
        print()
        print(f"  {_BOLD}Bare-server install:{_RESET}")
        print(f"  Copy {_CYAN}RVSconfig.yml{_RESET} to your server, then run:")
        print(f"  {_CYAN}curl -fsSL https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/install.sh | sudo bash{_RESET}")
        print()
        print(f"  See deployment guide: docs/deployment.md\n")

    except KeyboardInterrupt:
        print(f"\n{_YELLOW}Interrupted — no files written.{_RESET}")
        sys.exit(130)
