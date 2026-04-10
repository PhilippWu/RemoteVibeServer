"""Tests for the validators module."""

import unittest
from configurator.validators import (
    PreflightResult,
    run_preflight_checks,
    validate_api_key_nonempty,
    validate_api_key_optional,
    validate_callback_url_or_code,
    validate_cloudflare_api_token,
    validate_cloudflare_zone_id,
    validate_domain,
    validate_email,
    validate_oauth_client_id,
    validate_subdomain,
)


class TestValidateDomain(unittest.TestCase):
    def test_valid_domain(self):
        self.assertTrue(validate_domain("example.com"))

    def test_valid_subdomain_domain(self):
        self.assertTrue(validate_domain("sub.example.com"))

    def test_empty(self):
        self.assertIsInstance(validate_domain(""), str)

    def test_no_tld(self):
        self.assertIsInstance(validate_domain("example"), str)

    def test_spaces(self):
        # Leading/trailing spaces are stripped
        self.assertTrue(validate_domain("  example.com  "))


class TestValidateSubdomain(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_subdomain("dev"))

    def test_with_hyphen(self):
        self.assertTrue(validate_subdomain("my-dev"))

    def test_empty(self):
        self.assertIsInstance(validate_subdomain(""), str)

    def test_starts_with_hyphen(self):
        self.assertIsInstance(validate_subdomain("-bad"), str)

    def test_spaces_stripped(self):
        self.assertTrue(validate_subdomain("  dev  "))


class TestValidateEmail(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_email("admin@example.com"))

    def test_empty(self):
        self.assertIsInstance(validate_email(""), str)

    def test_no_at(self):
        self.assertIsInstance(validate_email("invalid"), str)


class TestValidateCloudflareApiToken(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_cloudflare_api_token("a" * 40))

    def test_empty(self):
        self.assertIsInstance(validate_cloudflare_api_token(""), str)

    def test_too_short(self):
        self.assertIsInstance(validate_cloudflare_api_token("short"), str)


class TestValidateCloudflareZoneId(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_cloudflare_zone_id("a" * 32))

    def test_valid_hex(self):
        self.assertTrue(validate_cloudflare_zone_id("0123456789abcdef" * 2))

    def test_empty(self):
        self.assertIsInstance(validate_cloudflare_zone_id(""), str)

    def test_wrong_length(self):
        self.assertIsInstance(validate_cloudflare_zone_id("abc"), str)

    def test_non_hex(self):
        self.assertIsInstance(validate_cloudflare_zone_id("g" * 32), str)


class TestValidateApiKey(unittest.TestCase):
    def test_optional_empty(self):
        self.assertTrue(validate_api_key_optional(""))

    def test_optional_value(self):
        self.assertTrue(validate_api_key_optional("sk-abc123"))

    def test_nonempty_with_value(self):
        self.assertTrue(validate_api_key_nonempty("sk-abc123"))

    def test_nonempty_empty(self):
        self.assertIsInstance(validate_api_key_nonempty(""), str)

    def test_nonempty_whitespace(self):
        self.assertIsInstance(validate_api_key_nonempty("   "), str)


class TestValidateOAuthClientId(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_oauth_client_id("Iv1.abc123def456"))

    def test_empty(self):
        self.assertIsInstance(validate_oauth_client_id(""), str)

    def test_whitespace_only(self):
        self.assertIsInstance(validate_oauth_client_id("   "), str)

    def test_contains_space(self):
        self.assertIsInstance(validate_oauth_client_id("bad client"), str)

    def test_contains_newline(self):
        self.assertIsInstance(validate_oauth_client_id("bad\nclient"), str)

    def test_contains_tab(self):
        self.assertIsInstance(validate_oauth_client_id("bad\tclient"), str)

    def test_non_printable(self):
        self.assertIsInstance(validate_oauth_client_id("bad\x00client"), str)

    def test_spaces_stripped(self):
        self.assertTrue(validate_oauth_client_id("  Iv1.abc123  "))


class TestValidateCallbackUrlOrCode(unittest.TestCase):
    def test_bare_code(self):
        self.assertTrue(validate_callback_url_or_code("abc123"))

    def test_full_url(self):
        self.assertTrue(validate_callback_url_or_code("https://example.com?code=abc"))

    def test_empty(self):
        self.assertIsInstance(validate_callback_url_or_code(""), str)

    def test_whitespace_only(self):
        self.assertIsInstance(validate_callback_url_or_code("   "), str)


class TestPreflightChecks(unittest.TestCase):
    def _full_config(self, **overrides):
        config = {
            "domain": "example.com",
            "subdomain": "dev",
            "email": "admin@example.com",
            "cloudflare_api_token": "a" * 40,
            "cloudflare_zone_id": "a" * 32,
            "coder_admin_password": "securepass1",
            "enable_agent_copilot": False,
            "enable_agent_claude": False,
            "enable_agent_gemini": False,
            "enable_agent_codex": False,
            "enable_agent_opencode": False,
            "openai_api_key": "",
            "anthropic_api_key": "",
            "google_api_key": "",
            "github_token": "",
            "codex_openai_auth_code": "",
            "opencode_provider": "",
        }
        config.update(overrides)
        return config

    def test_all_pass_no_agents(self):
        results = run_preflight_checks(self._full_config(), provider="aws")
        for r in results:
            self.assertTrue(r.passed, f"Check '{r.name}' failed: {r.message}")

    def test_missing_domain(self):
        results = run_preflight_checks(self._full_config(domain=""), provider="aws")
        required_check = results[0]
        self.assertFalse(required_check.passed)
        self.assertIn("domain", required_check.message)

    def test_copilot_without_token(self):
        config = self._full_config(enable_agent_copilot=True, github_token="")
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("Copilot", agent_check.message)

    def test_copilot_with_token(self):
        config = self._full_config(enable_agent_copilot=True, github_token="ghp_test123")
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_opencode_needs_any_key(self):
        config = self._full_config(enable_agent_opencode=True)
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("OpenCode", agent_check.message)

    def test_opencode_with_openai_key(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="openai",
            openai_api_key="sk-test",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_opencode_zen_needs_github_token(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("GITHUB_TOKEN", agent_check.message)

    def test_opencode_zen_with_github_token(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen",
            github_token="ghp_test",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_opencode_anthropic_needs_key(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="anthropic",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("ANTHROPIC_API_KEY", agent_check.message)

    def test_opencode_google_needs_key(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="google",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("GOOGLE_API_KEY", agent_check.message)

    def test_codex_needs_key(self):
        config = self._full_config(enable_agent_codex=True)
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("Codex", agent_check.message)

    def test_codex_with_github_token(self):
        config = self._full_config(enable_agent_codex=True, github_token="ghp_test")
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_codex_with_openai_key(self):
        config = self._full_config(enable_agent_codex=True, openai_api_key="sk-test")
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_codex_with_openai_auth_code(self):
        config = self._full_config(enable_agent_codex=True, codex_openai_auth_code="auth_code_test")
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_hetzner_hcloud_check_included(self):
        results = run_preflight_checks(self._full_config(), provider="hetzner")
        check_names = [r.name for r in results]
        self.assertIn("hcloud CLI", check_names)

    def test_non_hetzner_no_hcloud_check(self):
        results = run_preflight_checks(self._full_config(), provider="aws")
        check_names = [r.name for r in results]
        self.assertNotIn("hcloud CLI", check_names)

    def test_multiple_agents_missing_keys(self):
        config = self._full_config(
            enable_agent_copilot=True,
            enable_agent_claude=True,
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("Copilot", agent_check.message)
        self.assertIn("Claude", agent_check.message)

    def test_opencode_multi_provider_all_keys_present(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen,openai,anthropic",
            github_token="ghp_test",
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertTrue(agent_check.passed)

    def test_opencode_multi_provider_missing_one_key(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen,openai",
            github_token="ghp_test",
            # openai_api_key is missing
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("OPENAI_API_KEY", agent_check.message)

    def test_opencode_multi_provider_all_missing(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="opencode-zen,google",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("GITHUB_TOKEN", agent_check.message)
        self.assertIn("GOOGLE_API_KEY", agent_check.message)

    def test_opencode_unknown_provider_rejected(self):
        config = self._full_config(
            enable_agent_opencode=True,
            opencode_provider="unknown-provider",
            github_token="ghp_test",
        )
        results = run_preflight_checks(config, provider="aws")
        agent_check = results[1]
        self.assertFalse(agent_check.passed)
        self.assertIn("not supported", agent_check.message)


class TestPreflightResult(unittest.TestCase):
    def test_repr_pass(self):
        r = PreflightResult("test", True, "OK")
        self.assertIn("PASS", repr(r))

    def test_repr_fail(self):
        r = PreflightResult("test", False, "bad")
        self.assertIn("FAIL", repr(r))


if __name__ == "__main__":
    unittest.main()
