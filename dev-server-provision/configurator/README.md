# RemoteVibeServer — Interactive Configurator

Cross-platform CLI tool for generating `cloud-init.yaml` files and deploying RemoteVibeServer instances.

## Features

- **Interactive prompts** — guided step-by-step configuration
- **Multi-provider support** — Hetzner Cloud, AWS, GCP, Azure, DigitalOcean
- **AI agent setup** — configure Copilot, Claude, Gemini, Codex, and OpenCode with API keys or OAuth
- **Preflight checks** — validates configuration before generating output
- **YAML generation** — produces a ready-to-use `cloud-init.yaml`
- **RVSconfig.yml** — also generates a simple key-value config file for bare-server installs via `install.sh`
- **Hetzner CLI integration** — optionally executes `hcloud server create` directly
- **Cross-platform** — works on Windows, macOS, and Linux (Python 3.9+)

## Quick Start

### 1. Install dependencies

```bash
cd dev-server-provision/configurator
pip install -r requirements.txt
```

### 2. Run the configurator

```bash
# From the dev-server-provision directory:
python -m configurator
```

### 3. Follow the prompts

The configurator guides you through:

1. **Cloud provider selection** — choose your target provider
2. **Domain & DNS** — enter your domain, subdomain, and email
3. **Cloudflare configuration** — API token and zone ID
4. **AI agents** — select and configure coding agents
5. **Server options** — provider-specific settings (type, location, SSH key)
6. **Preflight checks** — automated validation of your configuration
7. **Output** — generates `cloud-init.yaml`
8. **Deploy** — shows deployment command (or executes it for Hetzner)

## Supported Providers

| Provider        | CLI Deploy | Server Selection | Location Selection |
|-----------------|:----------:|:----------------:|:------------------:|
| Hetzner Cloud   | ✅         | ✅               | ✅                 |
| AWS (EC2)       | —          | ✅               | —                  |
| Google Cloud    | —          | ✅               | —                  |
| Microsoft Azure | —          | ✅               | —                  |
| DigitalOcean    | —          | ✅               | —                  |

## AI Agents

| Agent            | Required Key        | Description                |
|------------------|---------------------|----------------------------|
| GitHub Copilot   | `GITHUB_TOKEN`      | GitHub Copilot CLI         |
| Claude Code      | `ANTHROPIC_API_KEY` | Anthropic Claude Code CLI  |
| Gemini CLI       | `GOOGLE_API_KEY`    | Google Gemini CLI          |
| Codex CLI        | `GITHUB_TOKEN`, `OPENAI_API_KEY`, or OpenAI OAuth | OpenAI Codex CLI |
| OpenCode AI      | Depends on provider¹ | Multi-provider AI agent   |

¹ OpenCode supports: OpenCode Zen, OpenCode Go (GitHub token), OpenAI, GitHub Copilot, Anthropic, Google.

Codex CLI supports three authentication modes: **Sign in with ChatGPT** (OpenAI Device Flow for Plus/Pro subscribers), **GitHub OAuth** (Device Flow), or **OpenAI API key**.

## Preflight Checks

The configurator validates:

- All required fields are provided (domain, email, Cloudflare credentials)
- Enabled agents have their corresponding API keys
- `hcloud` CLI is available (when using Hetzner provider)

## Running Tests

```bash
cd dev-server-provision
python -m unittest discover -s configurator/tests -v
```

## Requirements

- Python 3.9+
- [InquirerPy](https://github.com/kazhala/InquirerPy) — interactive prompts
