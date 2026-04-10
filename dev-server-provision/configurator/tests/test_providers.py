"""Tests for the providers module."""

import unittest
from configurator.providers import (
    PROVIDERS,
    AWSProvider,
    AzureProvider,
    DigitalOceanProvider,
    GCPProvider,
    HetznerProvider,
    get_provider,
    provider_choices,
)


class TestProviderRegistry(unittest.TestCase):
    def test_hetzner_in_registry(self):
        self.assertIn("hetzner", PROVIDERS)

    def test_aws_in_registry(self):
        self.assertIn("aws", PROVIDERS)

    def test_gcp_in_registry(self):
        self.assertIn("gcp", PROVIDERS)

    def test_azure_in_registry(self):
        self.assertIn("azure", PROVIDERS)

    def test_digitalocean_in_registry(self):
        self.assertIn("digitalocean", PROVIDERS)

    def test_get_provider(self):
        p = get_provider("hetzner")
        self.assertIsInstance(p, HetznerProvider)

    def test_get_provider_unknown(self):
        with self.assertRaises(KeyError):
            get_provider("nonexistent")


class TestProviderChoices(unittest.TestCase):
    def test_returns_list(self):
        choices = provider_choices()
        self.assertIsInstance(choices, list)
        self.assertGreater(len(choices), 0)

    def test_choice_structure(self):
        choices = provider_choices()
        for choice in choices:
            self.assertIn("name", choice)
            self.assertIn("value", choice)


class TestHetznerProvider(unittest.TestCase):
    def setUp(self):
        self.provider = HetznerProvider()

    def test_has_server_types(self):
        self.assertGreater(len(self.provider.server_types), 0)

    def test_has_locations(self):
        self.assertGreater(len(self.provider.locations), 0)

    def test_deployment_command_basic(self):
        cmd = self.provider.deployment_command({
            "server_type": "cpx31",
            "location": "nbg1 — Nuremberg, DE",
            "server_name": "my-server",
            "ssh_key": "my-key",
            "output_file": "cloud-init.yaml",
        })
        self.assertIn("hcloud server create", cmd)
        self.assertIn("--type cpx31", cmd)
        self.assertIn("--location nbg1", cmd)
        self.assertIn("--name my-server", cmd)
        self.assertIn("--ssh-key my-key", cmd)
        self.assertIn("--user-data-from-file cloud-init.yaml", cmd)

    def test_deployment_command_no_ssh_key(self):
        cmd = self.provider.deployment_command({
            "server_type": "cpx31",
            "location": "nbg1",
            "server_name": "dev-server",
            "ssh_key": "",
            "output_file": "cloud-init.yaml",
        })
        self.assertNotIn("--ssh-key", cmd)

    def test_deployment_command_defaults(self):
        cmd = self.provider.deployment_command({})
        self.assertIn("hcloud server create", cmd)
        self.assertIn("ubuntu-24.04", cmd)

    def test_deployment_command_quotes_spaces(self):
        cmd = self.provider.deployment_command({
            "server_type": "cpx31",
            "location": "nbg1",
            "server_name": "my dev server",
            "ssh_key": "",
            "output_file": "cloud-init.yaml",
        })
        self.assertIn("'my dev server'", cmd)

    def test_deployment_argv_basic(self):
        argv = self.provider.deployment_argv({
            "server_type": "cpx31",
            "location": "nbg1 — Nuremberg, DE",
            "server_name": "my-server",
            "ssh_key": "my-key",
            "output_file": "cloud-init.yaml",
        })
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[0], "hcloud")
        self.assertIn("--name", argv)
        name_idx = argv.index("--name")
        self.assertEqual(argv[name_idx + 1], "my-server")
        self.assertIn("--ssh-key", argv)
        ssh_idx = argv.index("--ssh-key")
        self.assertEqual(argv[ssh_idx + 1], "my-key")

    def test_deployment_argv_no_ssh_key(self):
        argv = self.provider.deployment_argv({
            "server_type": "cpx31",
            "location": "nbg1",
            "server_name": "dev-server",
            "ssh_key": "",
            "output_file": "cloud-init.yaml",
        })
        self.assertNotIn("--ssh-key", argv)

    def test_deployment_argv_preserves_spaces(self):
        argv = self.provider.deployment_argv({
            "server_type": "cpx31",
            "location": "nbg1",
            "server_name": "my dev server",
            "ssh_key": "",
            "output_file": "cloud-init.yaml",
        })
        name_idx = argv.index("--name")
        self.assertEqual(argv[name_idx + 1], "my dev server")


class TestAWSProvider(unittest.TestCase):
    def test_deployment_command(self):
        provider = AWSProvider()
        cmd = provider.deployment_command({})
        self.assertIn("aws ec2", cmd)

    def test_deployment_argv_returns_none(self):
        provider = AWSProvider()
        self.assertIsNone(provider.deployment_argv({}))


class TestGCPProvider(unittest.TestCase):
    def test_deployment_command(self):
        provider = GCPProvider()
        cmd = provider.deployment_command({})
        self.assertIn("gcloud", cmd)


class TestAzureProvider(unittest.TestCase):
    def test_deployment_command(self):
        provider = AzureProvider()
        cmd = provider.deployment_command({})
        self.assertIn("az vm create", cmd)


class TestDigitalOceanProvider(unittest.TestCase):
    def test_deployment_command(self):
        provider = DigitalOceanProvider()
        cmd = provider.deployment_command({})
        self.assertIn("doctl", cmd)


class TestServerTypeStr(unittest.TestCase):
    def test_str(self):
        st = HetznerProvider().server_types[0]
        self.assertEqual(str(st), st.label)


if __name__ == "__main__":
    unittest.main()
