"""Cloud provider definitions and deployment commands."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass
class ServerType:
    """Represents a cloud provider server/instance type."""

    name: str
    vcpus: int
    ram_gb: int
    disk_gb: int
    label: str  # Human-friendly label for the selector

    def __str__(self) -> str:
        return self.label


@dataclass
class Provider:
    """Cloud provider metadata and deployment command templates."""

    id: str
    name: str
    server_types: list[ServerType] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    deploy_hint: str = ""

    def deployment_command(self, config: dict) -> str:
        """Return a shell command or instruction for deploying with this provider."""
        raise NotImplementedError

    def deployment_argv(self, config: dict) -> list[str] | None:
        """Return an argv list for direct execution, or ``None`` if not supported."""
        return None


# ---------------------------------------------------------------------------
# Hetzner Cloud
# ---------------------------------------------------------------------------

class HetznerProvider(Provider):
    def __init__(self) -> None:
        super().__init__(
            id="hetzner",
            name="Hetzner Cloud",
            server_types=[
                ServerType("cpx21", 3, 4, 80, "CPX21 — 3 vCPU, 4 GB RAM, 80 GB (min)"),
                ServerType("cpx31", 4, 8, 160, "CPX31 — 4 vCPU, 8 GB RAM, 160 GB (recommended)"),
                ServerType("cpx41", 8, 16, 240, "CPX41 — 8 vCPU, 16 GB RAM, 240 GB"),
                ServerType("cpx51", 16, 32, 360, "CPX51 — 16 vCPU, 32 GB RAM, 360 GB"),
            ],
            locations=[
                "nbg1 — Nuremberg, DE",
                "fsn1 — Falkenstein, DE",
                "hel1 — Helsinki, FI",
                "ash — Ashburn, US",
                "hil — Hillsboro, US",
            ],
            deploy_hint="Requires the `hcloud` CLI — https://github.com/hetznercloud/cli",
        )

    def deployment_command(self, config: dict) -> str:
        server_type = config.get("server_type", "cpx31")
        location = config.get("location", "nbg1").split()[0].strip()
        server_name = config.get("server_name", "dev-server")
        ssh_key = config.get("ssh_key", "")
        output_file = config.get("output_file", "cloud-init.yaml")

        parts = [
            "hcloud server create",
            f"  --name {shlex.quote(server_name)}",
            f"  --type {shlex.quote(server_type)}",
            "  --image ubuntu-24.04",
            f"  --location {shlex.quote(location)}",
        ]
        if ssh_key:
            parts.append(f"  --ssh-key {shlex.quote(ssh_key)}")
        parts.append(f"  --user-data-from-file {shlex.quote(output_file)}")

        return " \\\n".join(parts)

    def deployment_argv(self, config: dict) -> list[str] | None:
        server_type = config.get("server_type", "cpx31")
        location = config.get("location", "nbg1").split()[0].strip()
        server_name = config.get("server_name", "dev-server")
        ssh_key = config.get("ssh_key", "")
        output_file = config.get("output_file", "cloud-init.yaml")

        argv = [
            "hcloud", "server", "create",
            "--name", server_name,
            "--type", server_type,
            "--image", "ubuntu-24.04",
            "--location", location,
        ]
        if ssh_key:
            argv.extend(["--ssh-key", ssh_key])
        argv.extend(["--user-data-from-file", output_file])
        return argv


# ---------------------------------------------------------------------------
# AWS EC2
# ---------------------------------------------------------------------------

class AWSProvider(Provider):
    def __init__(self) -> None:
        super().__init__(
            id="aws",
            name="AWS (EC2)",
            server_types=[
                ServerType("t3.medium", 2, 4, 0, "t3.medium — 2 vCPU, 4 GB RAM"),
                ServerType("t3.large", 2, 8, 0, "t3.large — 2 vCPU, 8 GB RAM"),
                ServerType("t3.xlarge", 4, 16, 0, "t3.xlarge — 4 vCPU, 16 GB RAM"),
            ],
            deploy_hint="Use the UserData field in EC2 launch configuration.",
        )

    def deployment_command(self, config: dict) -> str:
        return (
            "# Paste the generated cloud-init.yaml contents into the\n"
            "# 'User data' field of your EC2 launch configuration,\n"
            "# or use the AWS CLI:\n"
            "#   aws ec2 run-instances --user-data file://cloud-init.yaml ..."
        )


# ---------------------------------------------------------------------------
# GCP
# ---------------------------------------------------------------------------

class GCPProvider(Provider):
    def __init__(self) -> None:
        super().__init__(
            id="gcp",
            name="Google Cloud (GCE)",
            server_types=[
                ServerType("e2-medium", 2, 4, 0, "e2-medium — 2 vCPU, 4 GB RAM"),
                ServerType("e2-standard-4", 4, 16, 0, "e2-standard-4 — 4 vCPU, 16 GB RAM"),
            ],
            deploy_hint="Set metadata.user-data on a cloud-init compatible image.",
        )

    def deployment_command(self, config: dict) -> str:
        return (
            "# Set the cloud-init data via instance metadata:\n"
            "#   gcloud compute instances create dev-server \\\n"
            '#     --metadata-from-file user-data=cloud-init.yaml ...'
        )


# ---------------------------------------------------------------------------
# Azure
# ---------------------------------------------------------------------------

class AzureProvider(Provider):
    def __init__(self) -> None:
        super().__init__(
            id="azure",
            name="Microsoft Azure",
            server_types=[
                ServerType("Standard_B2s", 2, 4, 0, "Standard_B2s — 2 vCPU, 4 GB RAM"),
                ServerType("Standard_B2ms", 2, 8, 0, "Standard_B2ms — 2 vCPU, 8 GB RAM"),
            ],
            deploy_hint="Use Custom Data in the VM creation.",
        )

    def deployment_command(self, config: dict) -> str:
        return (
            "# Use --custom-data when creating the VM:\n"
            "#   az vm create --custom-data cloud-init.yaml ..."
        )


# ---------------------------------------------------------------------------
# DigitalOcean
# ---------------------------------------------------------------------------

class DigitalOceanProvider(Provider):
    def __init__(self) -> None:
        super().__init__(
            id="digitalocean",
            name="DigitalOcean",
            server_types=[
                ServerType("s-2vcpu-4gb", 2, 4, 80, "s-2vcpu-4gb — 2 vCPU, 4 GB RAM"),
                ServerType("s-4vcpu-8gb", 4, 8, 160, "s-4vcpu-8gb — 4 vCPU, 8 GB RAM"),
            ],
            deploy_hint="Paste into the 'User data' field when creating a Droplet.",
        )

    def deployment_command(self, config: dict) -> str:
        return (
            "# Paste the cloud-init.yaml contents into the 'User data'\n"
            "# field when creating a DigitalOcean Droplet, or use the CLI:\n"
            "#   doctl compute droplet create dev-server \\\n"
            "#     --user-data-file cloud-init.yaml ..."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in [
        HetznerProvider(),
        AWSProvider(),
        GCPProvider(),
        AzureProvider(),
        DigitalOceanProvider(),
    ]
}


def get_provider(provider_id: str) -> Provider:
    """Return a provider by ID or raise *KeyError*."""
    return PROVIDERS[provider_id]


def provider_choices() -> list[dict[str, str]]:
    """Return a list of ``{"name": ..., "value": ...}`` dicts for prompt choices."""
    return [{"name": p.name, "value": p.id} for p in PROVIDERS.values()]
