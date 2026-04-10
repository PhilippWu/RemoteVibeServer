"""Tests for the generator module."""

import unittest
from configurator.generator import default_config, generate_cloud_init, generate_rvs_config


class TestDefaultConfig(unittest.TestCase):
    def test_has_all_required_keys(self):
        config = default_config()
        required = [
            "domain", "subdomain", "email",
            "cloudflare_api_token", "cloudflare_zone_id",
            "enable_agent_copilot", "enable_agent_claude",
            "enable_agent_gemini", "enable_agent_codex",
            "enable_agent_opencode",
            "openai_api_key", "anthropic_api_key",
            "google_api_key", "github_token",
            "codex_openai_auth_code",
            "opencode_provider",
        ]
        for key in required:
            self.assertIn(key, config, f"Missing key: {key}")

    def test_agents_default_false(self):
        config = default_config()
        for key in ("enable_agent_copilot", "enable_agent_claude",
                     "enable_agent_gemini", "enable_agent_codex",
                     "enable_agent_opencode"):
            self.assertFalse(config[key])


class TestGenerateCloudInit(unittest.TestCase):
    def _sample_config(self, **overrides):
        config = default_config()
        config.update({
            "domain": "example.com",
            "subdomain": "dev",
            "email": "admin@example.com",
            "cloudflare_api_token": "cf_token_test",
            "cloudflare_zone_id": "zone_id_test",
        })
        config.update(overrides)
        return config

    def test_starts_with_cloud_config(self):
        result = generate_cloud_init(self._sample_config())
        self.assertTrue(result.startswith("#cloud-config"))

    def test_contains_domain(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("DOMAIN=example.com", result)

    def test_contains_subdomain(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("SUBDOMAIN=dev", result)

    def test_contains_email(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("EMAIL=admin@example.com", result)

    def test_contains_cloudflare_token(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("CLOUDFLARE_API_TOKEN=cf_token_test", result)

    def test_contains_cloudflare_zone_id(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("CLOUDFLARE_ZONE_ID=zone_id_test", result)

    def test_coder_url_computed(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("CODER_URL=https://dev.example.com", result)

    def test_agents_false_by_default(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("ENABLE_AGENT_COPILOT=false", result)
        self.assertIn("ENABLE_AGENT_CLAUDE=false", result)
        self.assertIn("ENABLE_AGENT_CODEX=false", result)

    def test_agent_enabled(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_copilot=True,
            github_token="ghp_test",
        ))
        self.assertIn("ENABLE_AGENT_COPILOT=true", result)
        self.assertIn("GITHUB_TOKEN=ghp_test", result)

    def test_contains_bootstrap_script(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("/etc/dev-server/bootstrap.sh", result)
        self.assertIn("set -euo pipefail", result)

    def test_bootstrap_exports_home(self):
        """Generated bootstrap.sh must set HOME for cloud-init's minimal env."""
        result = generate_cloud_init(self._sample_config())
        self.assertIn('export HOME="${HOME:-/root}"', result)

    def test_contains_runcmd(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("runcmd:", result)
        self.assertIn("docker", result)
        self.assertIn("ufw", result)

    def test_contains_packages(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("packages:", result)
        self.assertIn("- curl", result)
        self.assertIn("- fail2ban", result)

    def test_final_message(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("final_message:", result)
        self.assertIn("RemoteVibeServer provisioning complete", result)

    def test_no_placeholders_remain(self):
        """Ensure no ``<PLACEHOLDER>`` patterns survive generation."""
        result = generate_cloud_init(self._sample_config())
        self.assertNotIn("<YOUR_", result)

    def test_bool_normalisation(self):
        result = generate_cloud_init(self._sample_config(enable_agent_claude=True))
        self.assertIn("ENABLE_AGENT_CLAUDE=true", result)

    def test_multiple_agents(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_copilot=True,
            enable_agent_claude=True,
            enable_agent_opencode=True,
            github_token="ghp_test",
            anthropic_api_key="sk-ant-test",
            openai_api_key="sk-test",
        ))
        self.assertIn("ENABLE_AGENT_COPILOT=true", result)
        self.assertIn("ENABLE_AGENT_CLAUDE=true", result)
        self.assertIn("ENABLE_AGENT_OPENCODE=true", result)
        self.assertIn("GITHUB_TOKEN=ghp_test", result)
        self.assertIn("ANTHROPIC_API_KEY=sk-ant-test", result)
        self.assertIn("OPENAI_API_KEY=sk-test", result)

    def test_codex_agent_enabled(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_codex=True,
            openai_api_key="sk-codex-test",
        ))
        self.assertIn("ENABLE_AGENT_CODEX=true", result)
        self.assertIn("OPENAI_API_KEY=sk-codex-test", result)

    def test_codex_openai_auth_code(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_codex=True,
            codex_openai_auth_code="auth_code_test",
        ))
        self.assertIn("CODEX_OPENAI_AUTH_CODE=auth_code_test", result)

    def test_opencode_provider_written(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen",
            github_token="ghp_test",
        ))
        self.assertIn("OPENCODE_PROVIDER=opencode-zen", result)

    def test_opencode_provider_empty_by_default(self):
        result = generate_cloud_init(self._sample_config())
        self.assertIn("OPENCODE_PROVIDER=", result)

    def test_opencode_multi_provider_written(self):
        result = generate_cloud_init(self._sample_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen,openai,anthropic",
            github_token="ghp_test",
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
        ))
        self.assertIn("OPENCODE_PROVIDER=opencode-zen,openai,anthropic", result)


class TestGenerateRvsConfig(unittest.TestCase):
    """Tests for generate_rvs_config()."""

    def _sample_config(self, **overrides):
        config = default_config()
        config.update({
            "domain": "example.com",
            "subdomain": "dev",
            "email": "admin@example.com",
            "cloudflare_api_token": "cf_token_test",
            "cloudflare_zone_id": "zone_id_test",
        })
        config.update(overrides)
        return config

    def test_starts_with_comment_header(self):
        result = generate_rvs_config(self._sample_config())
        self.assertTrue(result.startswith("# RVSconfig.yml"))

    def test_contains_domain(self):
        result = generate_rvs_config(self._sample_config())
        self.assertIn('domain: "example.com"', result)

    def test_contains_email(self):
        result = generate_rvs_config(self._sample_config())
        self.assertIn('email: "admin@example.com"', result)

    def test_bool_false_written_lowercase(self):
        result = generate_rvs_config(self._sample_config())
        self.assertIn("enable_agent_copilot: false", result)

    def test_bool_true_written_lowercase(self):
        result = generate_rvs_config(self._sample_config(enable_agent_claude=True))
        self.assertIn("enable_agent_claude: true", result)

    def test_empty_value_quoted(self):
        result = generate_rvs_config(self._sample_config())
        self.assertIn('openai_api_key: ""', result)

    def test_api_key_present(self):
        result = generate_rvs_config(self._sample_config(github_token="ghp_test"))
        self.assertIn('github_token: "ghp_test"', result)

    def test_all_keys_present(self):
        """Every key from default_config must appear."""
        config = self._sample_config()
        result = generate_rvs_config(config)
        for key in config:
            self.assertIn(f"{key}:", result, f"Missing key: {key}")

    def test_opencode_multi_provider(self):
        result = generate_rvs_config(self._sample_config(
            opencode_provider="opencode-zen,openai",
        ))
        self.assertIn('opencode_provider: "opencode-zen,openai"', result)

    def test_trailing_newline(self):
        result = generate_rvs_config(self._sample_config())
        self.assertTrue(result.endswith("\n"))

    def test_value_with_double_quote_is_escaped(self):
        result = generate_rvs_config(self._sample_config(domain='ex"ample.com'))
        self.assertIn(r'domain: "ex\"ample.com"', result)

    def test_value_with_backslash_is_escaped(self):
        result = generate_rvs_config(self._sample_config(domain=r"ex\ample.com"))
        self.assertIn(r'domain: "ex\\ample.com"', result)

    def test_value_with_newline_is_escaped(self):
        result = generate_rvs_config(self._sample_config(domain="line1\nline2"))
        self.assertIn(r'domain: "line1\nline2"', result)


if __name__ == "__main__":
    unittest.main()
