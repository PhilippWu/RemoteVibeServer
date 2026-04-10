# Contributing to RemoteVibeServer

Thank you for your interest in contributing! 🎉  
RemoteVibeServer is an early-stage open-source project and all contributions are welcome — from bug reports to new features and documentation improvements.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Project Structure](#project-structure)
- [Commit Style](#commit-style)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## Code of Conduct

Be kind, be constructive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## Ways to Contribute

| What | Where |
|---|---|
| 🐛 Bug report | [Open an issue](https://github.com/PhilippWu/RemoteVibeServer/issues/new) |
| 💡 Feature request | [Open an issue](https://github.com/PhilippWu/RemoteVibeServer/issues/new) |
| 🔧 Code fix / feature | Fork → branch → PR |
| 📝 Docs improvement | Same as above |
| 🧪 Test a deployment | Try it and report your experience |
| ⭐ Spread the word | Star the repo, share it |

---

## Getting Started

### Prerequisites

- Python 3.10+ (for the configurator)
- A Ubuntu VPS or local VM (for full deployment testing)
- Docker (for workspace testing)
- `git`

### Local setup

```bash
git clone https://github.com/PhilippWu/RemoteVibeServer.git
cd RemoteVibeServer

# Install configurator dependencies
pip install -r dev-server-provision/configurator/requirements.txt

# Run configurator tests
cd dev-server-provision/configurator
python -m pytest tests/ -v
```

### Testing a deployment

1. Copy `dev-server-provision/cloud-init.example.yaml` to `cloud-init.yaml`
2. Fill in your values (domain, Cloudflare token, etc.)
3. Create a fresh Ubuntu 22.04 server and pass `cloud-init.yaml` as user-data
4. Watch the log: `tail -f /var/log/dev-server-provision.log`

> ⚠️ **Never commit `cloud-init.yaml`** — it contains secrets and is gitignored.

---

## Development Workflow

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b fix/your-topic
   # or
   git checkout -b feat/your-feature
   ```
3. **Make your changes** (see project structure below)
4. **Test** — run the configurator tests and/or deploy to a test server
5. **Commit** using [Conventional Commits](#commit-style)
6. **Push** and open a Pull Request

---

## Project Structure

```
dev-server-provision/
├── setup.sh              # Main provisioning orchestrator
├── cloud-init.example.yaml  # Public template (no secrets)
├── infra/
│   ├── dns.sh            # Cloudflare DNS record management
│   ├── proxy.sh          # Caddy reverse proxy setup
│   └── agents.sh         # AI agent installation
├── coder/
│   ├── Dockerfile        # Workspace container image
│   ├── main.tf           # Terraform workspace template
│   └── devcontainer.json # VS Code devcontainer config
├── configurator/         # Python CLI configurator
│   ├── cli.py            # Entry point
│   ├── generator.py      # cloud-init.yaml generator
│   ├── oauth.py          # OAuth token helper
│   └── tests/            # pytest test suite
└── docs/                 # Architecture, deployment, security docs
```

**Key areas for contribution:**
- `configurator/` — Python, well-tested, great for first contributions
- `infra/*.sh` — bash scripts, test via real deployment
- `coder/main.tf` — Terraform, Coder workspace improvements
- `docs/` — always welcome

---

## Commit Style

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add IP-only deployment mode
fix: resolve Caddy permission issue on restart
docs: update deployment guide with IP-only section
refactor: extract DNS logic into separate function
test: add configurator validator tests
chore: bump requirements versions
```

---

## Pull Request Guidelines

- Target branch: `main`
- Keep PRs focused — one feature or fix per PR
- Include a clear description of **what** and **why**
- Reference any related issue: `Closes #1`
- Shell scripts: test on Ubuntu 22.04
- Python: keep existing test coverage green (`pytest tests/`)
- No secrets in code or commits

---

## Reporting Bugs

Please include:
- What you did (steps to reproduce)
- What you expected
- What actually happened
- Relevant log output (`/var/log/dev-server-provision.log`)
- Server OS and cloud provider

---

## Suggesting Features

Open an issue with the `enhancement` label and describe:
- The problem you're solving
- Your proposed solution
- Any alternatives you considered

---

## Questions?

Open a [GitHub Discussion](https://github.com/PhilippWu/RemoteVibeServer/discussions) or an issue tagged `question`.
