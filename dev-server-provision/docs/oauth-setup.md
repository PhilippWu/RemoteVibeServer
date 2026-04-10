# OAuth Setup for AI Agent Providers

This guide explains how to set up OAuth authentication for each AI coding
agent supported by the RemoteVibeServer configurator.

---

## Overview

| Agent           | Auth Method                | Client ID needed? | Flow                  |
|-----------------|----------------------------|--------------------|-----------------------|
| GitHub Copilot  | OAuth 2.0 Device Flow      | ✅ Yes (built-in)  | Device Flow           |
| Google Gemini   | OAuth 2.0 Authorization Code | ✅ Yes (user-provided) | Authorization Code |
| Anthropic Claude| Plain API Key              | ❌ No              | —                     |
| OpenAI Codex    | OpenAI Device Flow or GitHub OAuth or API Key | ✅ Built-in | Device Flow / API Key |
| OpenCode        | Reuses GitHub / API keys   | ❌ No              | Device Flow / API Key |

---

## 1. GitHub (Copilot & OpenCode)

GitHub uses the **OAuth 2.0 Device Flow** — the user visits a URL, enters a
short code, and the CLI polls until a token is issued. No callback URL is
needed.

### Get a Client ID

1. Go to <https://github.com/settings/applications/new>
2. **Application name:** e.g. `RemoteVibeServer`
3. **Homepage URL:** your server URL or `https://github.com/your/repo`
4. **Authorization callback URL:** set any valid URL (for example, your
   homepage URL or `http://localhost/callback`); GitHub may require this
   field, but it will not be used for Device Flow
5. **Enable Device Flow:** ✅ check this box
6. Click **Register application**
7. Copy the **Client ID** (starts with `Ov23li…`)

### Configure

The configurator has a built-in Client ID (`Ov23liu7cPhVnaUoWhUl`). To use
your own, set the environment variable:

```bash
export GITHUB_OAUTH_CLIENT_ID="Ov23li..."
```

Or update the constant `_GITHUB_OAUTH_CLIENT_ID` in
`configurator/oauth.py`.

### How it works

```
CLI                        GitHub
 │                            │
 ├─ POST /login/device/code ─►│  (client_id, scope=read:user)
 │◄─ device_code, user_code ──┤
 │                            │
 │  Print: "Open https://github.com/login/device"
 │  Print: "Enter code: ABCD-1234"
 │                            │
 ├─ POST /login/oauth/access_token ─►│  (poll every 5s)
 │◄─ access_token ────────────┤
```

### Scope

- `read:user` — sufficient for Copilot CLI and OpenCode

---

## 2. Google (Gemini CLI)

Google uses the standard **OAuth 2.0 Authorization Code** flow. The user
opens a URL in the browser, grants consent, and Google redirects to a local
callback with an authorization code.

### Get a Client ID

1. Go to <https://console.cloud.google.com/apis/credentials>
2. Create a project (or select an existing one)
3. Click **+ CREATE CREDENTIALS → OAuth client ID**
4. Application type: **Desktop app** (recommended for CLI)
5. Name: e.g. `RemoteVibeServer Gemini`
6. Click **Create**
7. Copy the **Client ID** and **Client Secret**

> **Note:** You also need to enable the **Generative Language API** in
> your project: <https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com>

### Configure

```bash
export GOOGLE_OAUTH_CLIENT_ID="123456789.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="GOCSPX-..."
```

The repository intentionally does not store Google OAuth credentials.

### How it works

```
CLI                           Google
 │                               │
 │  Build URL: accounts.google.com/o/oauth2/v2/auth
 │  Open browser → user grants consent
 │                               │
 │◄─ redirect to localhost:8085?code=… ─┤
 │                               │
 ├─ POST oauth2.googleapis.com/token ──►│  (code, client_id, client_secret)
 │◄─ access_token ───────────────┤
```

### Scope

- `https://www.googleapis.com/auth/generative-language`

### Helper functions in `oauth.py`

```python
from configurator.oauth import (
    build_google_authorization_url,
    exchange_google_authorization_code,
)

# Step 1: build the URL the user opens
url = build_google_authorization_url()  # uses GOOGLE_OAUTH_CLIENT_ID

# Step 2: after user grants consent and you receive the code:
token = exchange_google_authorization_code(code="4/0Axx...")
print(token.access_token)
```

---

## 3. Anthropic (Claude Code)

Anthropic does **not** offer OAuth. Authentication is via a plain API key.

### Get an API Key

1. Go to <https://console.anthropic.com/settings/keys>
2. Click **Create Key**
3. Copy the key (starts with `sk-ant-…`)

### Configure

The configurator asks for the key interactively, or set:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

> **Future-proofing:** `oauth.py` includes a placeholder
> `get_anthropic_client_id()` that returns `""`.  If Anthropic adds OAuth
> support later, you can set `ANTHROPIC_OAUTH_CLIENT_ID` without code
> changes.

---

## 4. OpenAI (Codex CLI)

Codex CLI supports three authentication modes:

### Option A: Sign in with ChatGPT (recommended for Plus/Pro users)

This is the **recommended** option for users with a ChatGPT Plus, Pro, Team,
or Enterprise subscription.  It uses OpenAI's own OAuth Device Flow, identical
to running `codex login --device-auth`.

- **Issuer**: `https://auth.openai.com`
- **Client ID**: `app_EMoamEEZ73f0CkXaXp7hrann` (built-in, override via `OPENAI_CODEX_CLIENT_ID`)
- **Device code endpoint**: `https://auth.openai.com/api/accounts/deviceauth/usercode`
- **Verification URL**: `https://auth.openai.com/codex/device`

The configurator runs this flow interactively: it requests a device code,
shows you a URL + code, and polls until you authorize in your browser.

> **Note**: This flow exchanges for an authorization code + PKCE values
> which Codex CLI uses on first launch.  No OpenAI API billing is needed —
> usage runs against your ChatGPT subscription.
> A **ChatGPT Plus, Pro, Team, or Enterprise** subscription is required.
> Free ChatGPT accounts do not have access to Codex CLI.

### Option B: GitHub Device Flow

Codex CLI can also authenticate via the same **GitHub OAuth Device Flow** used
by Copilot.  No separate registration is needed — the built-in GitHub Client
ID works.

Follow the steps in [section 1](#1-github-copilot--opencode) to obtain a
GitHub token.  The `GITHUB_TOKEN` will be used by Codex CLI automatically.

### Option C: OpenAI API Key

1. Go to <https://platform.openai.com/api-keys>
2. Click **Create new secret key**
3. Copy the key (starts with `sk-…`)

```bash
export OPENAI_API_KEY="sk-..."
```

> The configurator lets you choose between all three methods when enabling
> the Codex CLI agent.

---

## 5. OpenCode (multi-provider)

OpenCode delegates authentication to one of its upstream providers:

- **OpenCode Zen** (Recommended) → GitHub OAuth
- **OpenCode Go** → GitHub OAuth
- **OpenAI** → `OPENAI_API_KEY`
- **GitHub Copilot** → `GITHUB_TOKEN` (Device Flow)
- **Anthropic** → `ANTHROPIC_API_KEY`
- **Google** → `GOOGLE_API_KEY`

The configurator presents a provider selection menu matching the providers
shown in the OpenCode "Connect a provider" screen.

No separate OAuth registration is needed for OpenCode. Provide the API key
or GitHub token for your chosen provider.

---

## Environment Variables Summary

| Variable                      | Provider   | Required? |
|-------------------------------|------------|-----------|
| `GITHUB_OAUTH_CLIENT_ID`     | GitHub     | Built-in  |
| `GOOGLE_OAUTH_CLIENT_ID`     | Google     | Yes *     |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google     | Yes *     |
| `ANTHROPIC_API_KEY`           | Anthropic  | Yes *     |
| `ANTHROPIC_OAUTH_CLIENT_ID`  | Anthropic  | No (placeholder) |
| `OPENAI_API_KEY`              | Codex/OpenCode | Yes * |
| `OPENAI_OAUTH_CLIENT_ID`     | OpenAI     | No (placeholder) |
| `OPENAI_CODEX_CLIENT_ID`     | Codex CLI  | Built-in  |
| `CODEX_OPENAI_AUTH_CODE`      | Codex CLI  | No (OAuth flow) |
| `OPENCODE_PROVIDER`           | OpenCode   | No        |

\* Only required if the corresponding agent is enabled.

---

## 6. Codex CLI in headless / SSH environments

When `ENABLE_AGENT_CODEX=true` is set and the server is provisioned via
`cloud-init` or `install.sh`, there is no interactive terminal available for
browser-based OAuth flows.  The Codex CLI would hang waiting for user input
if no credential is pre-configured.

### How authentication is resolved (in order)

| Priority | Credential | How to obtain |
|----------|------------|---------------|
| 1 (best) | `CODEX_OPENAI_AUTH_CODE` | Run the configurator before provisioning and complete the OpenAI Device Flow there. The code is embedded in the generated config. |
| 2 | `OPENAI_API_KEY` | Create a key at <https://platform.openai.com/api-keys> |
| 3 | `GITHUB_TOKEN` | GitHub OAuth Device Flow (same as Copilot) |
| — | None set | `agents.sh` prints a warning and skips; workspace startup script prints the Device Flow URL |

### Path 1 — pre-obtain the auth code with the configurator (recommended)

```bash
# On your local machine, before provisioning:
python -m configurator
# → Enable Codex
# → Choose "Sign in with ChatGPT (Device Flow)"
# → Complete auth in browser
# The code is saved as CODEX_OPENAI_AUTH_CODE in cloud-init.yaml / RVSconfig.yml
```

At workspace start, the startup script runs:
```bash
codex login --auth-code "$CODEX_OPENAI_AUTH_CODE"
```
This completes the PKCE exchange non-interactively — no browser needed on the
server side.

### Path 2 — API key

Add to `/etc/dev-server/env`:
```
OPENAI_API_KEY=sk-...
```

### Path 3 — post-provisioning manual auth

If the workspace is already running, open a terminal inside it and run:
```bash
codex login --device-auth
# Follow the URL that is printed:
# https://auth.openai.com/codex/device
```

### Reading the Device Flow URL from the log

When no credential is set at provisioning time, `agents.sh` logs the following
(visible in `/var/log/dev-server-provision.log`):

```
[agents] WARN: Device Flow URL (for manual auth):  https://auth.openai.com/codex/device
```

The workspace startup script also echoes the URL on first start so it appears
in the Coder workspace log panel.

---

## Adding a new provider

To add OAuth for a new AI agent:

1. **Register an OAuth app** with the provider and note the Client ID
   (and Client Secret if needed).
2. **Add constants** in `configurator/oauth.py`:
   ```python
   _NEWPROVIDER_OAUTH_CLIENT_ID = ""
   _NEWPROVIDER_OAUTH_CLIENT_SECRET = ""
   ```
3. **Add getter functions**:
   ```python
   def get_newprovider_client_id() -> str:
       return os.environ.get("NEWPROVIDER_OAUTH_CLIENT_ID", "").strip() or _NEWPROVIDER_OAUTH_CLIENT_ID
   ```
4. **Add convenience helpers** (e.g. `build_newprovider_authorization_url()`).
5. **Wire it into `cli.py`** — follow the pattern in `_ask_github_token_oauth()`.
6. **Add tests** in `configurator/tests/test_oauth.py`.
