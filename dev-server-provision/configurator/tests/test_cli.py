"""Tests for the cli module – specifically helpers and OAuth output."""

import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from configurator.cli import _clickable_url


# ---------------------------------------------------------------------------
# _clickable_url
# ---------------------------------------------------------------------------

class TestClickableUrl(unittest.TestCase):
    """Tests for the OSC 8 terminal hyperlink helper."""

    def test_url_only(self):
        result = _clickable_url("https://example.com")
        self.assertIn("https://example.com", result)
        # Should contain OSC 8 open and close sequences
        self.assertTrue(result.startswith("\033]8;;"))
        self.assertTrue(result.endswith("\033]8;;\033\\"))

    def test_with_label(self):
        result = _clickable_url("https://example.com", label="Click here")
        self.assertIn("Click here", result)
        self.assertIn("https://example.com", result)

    def test_label_none_defaults_to_url(self):
        url = "https://github.com/login/device"
        result = _clickable_url(url, label=None)
        # The display text should be the URL itself
        self.assertIn(url, result)

    def test_label_empty_string_defaults_to_url(self):
        url = "https://github.com/login/device"
        result = _clickable_url(url, label="")
        # Empty string is falsy, so display should fall back to url
        self.assertIn(url, result)


# ---------------------------------------------------------------------------
# _ask_github_token_oauth – browser fallback message
# ---------------------------------------------------------------------------

def _make_device_code_mock(verification_uri_complete=""):
    """Create a mock DeviceCodeResponse with optional complete URI."""
    dc = MagicMock()
    dc.verification_uri = "https://github.com/login/device"
    dc.verification_uri_complete = verification_uri_complete
    dc.user_code = "ABCD-1234"
    dc.device_code = "dc_test"
    dc.interval = 5
    dc.expires_in = 900
    return dc


class TestAskGithubTokenOAuthOutput(unittest.TestCase):
    """Verify that the OAuth flow uses built-in Client ID without prompting."""

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_shows_fallback_when_browser_fails(self, mock_inq, mock_oauth, mock_wb):
        """When webbrowser.open returns False, a manual-open hint is printed."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = False

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn("Could not open a browser automatically", output)
        self.assertIn("Please copy the URL above and open it in your browser", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_no_fallback_when_browser_opens(self, mock_inq, mock_oauth, mock_wb):
        """When webbrowser.open returns True, no fallback message is shown."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertNotIn("Could not open a browser automatically", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_shows_osc8_link(self, mock_inq, mock_oauth, mock_wb):
        """The verification URL should be wrapped in an OSC 8 hyperlink."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn("\033]8;;https://github.com/login/device\033\\", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_fallback_when_browser_raises(self, mock_inq, mock_oauth, mock_wb):
        """When webbrowser.open raises an exception, fallback hint is shown."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.side_effect = OSError("no display")

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn("Could not open a browser automatically", output)
        self.assertIn("Please copy the URL above and open it in your browser", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_uses_complete_uri_when_available(self, mock_inq, mock_oauth, mock_wb):
        """When verification_uri_complete is set, it should be used for links."""
        from configurator.cli import _ask_github_token_oauth

        complete_uri = "https://github.com/login/device?user_code=ABCD-1234"
        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock(
            verification_uri_complete=complete_uri
        )
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn(complete_uri, output)
        mock_wb.open.assert_called_once_with(complete_uri)
        self.assertIn("pre-filled", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_shows_plain_text_url(self, mock_inq, mock_oauth, mock_wb):
        """The plain-text URL should always be printed for easy copying."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        url = "https://github.com/login/device"
        self.assertGreaterEqual(output.count(url), 2)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_shows_user_code_when_no_complete_uri(self, mock_inq, mock_oauth, mock_wb):
        """When no verification_uri_complete, user code must be shown for manual entry."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn("Enter code", output)
        self.assertIn("ABCD-1234", output)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_no_client_id_prompt(self, mock_inq, mock_oauth, mock_wb):
        """The Client ID should never be prompted — it comes from config."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.test_client_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        # inquirer.text should NOT be called (no Client ID prompt)
        mock_inq.text.assert_not_called()
        # get_github_client_id should be called instead
        mock_oauth.get_github_client_id.assert_called_once()

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_missing_client_id_shows_setup_instructions(self, mock_inq, mock_oauth):
        """When no Client ID is configured, setup instructions are shown."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = ""
        mock_oauth.OAuthError = Exception
        mock_inq.secret.return_value.execute.return_value = "ghp_manual"

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _ask_github_token_oauth(config)

        output = mock_stdout.getvalue()
        self.assertIn("No GitHub OAuth Client ID configured", output)
        self.assertIn("GITHUB_OAUTH_CLIENT_ID", output)
        self.assertIn("github.com/settings/applications/new", output)
        # Should fall back to manual token entry
        self.assertEqual(config["github_token"], "ghp_manual")

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_client_id_passed_to_device_code_request(self, mock_inq, mock_oauth, mock_wb):
        """The resolved Client ID should be passed to request_github_device_code."""
        from configurator.cli import _ask_github_token_oauth

        mock_oauth.get_github_client_id.return_value = "Iv1.my_app_id"
        mock_oauth.request_github_device_code.return_value = _make_device_code_mock()
        mock_oauth.OAuthError = Exception

        token = MagicMock()
        token.access_token = "ghp_test_token"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        mock_oauth.request_github_device_code.assert_called_once_with("Iv1.my_app_id")


# ---------------------------------------------------------------------------
# Device-flow recovery (retry / manual / skip)
# ---------------------------------------------------------------------------

class TestGithubOAuthRetrySkip(unittest.TestCase):
    """Verify the retry / manual / skip behaviour on Device Flow failure."""

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_retry_then_success(self, mock_inq, mock_oauth, mock_wb):
        """User chooses Retry after initial failure; second attempt succeeds."""
        from configurator.cli import _ask_github_token_oauth, _RECOVER_RETRY

        mock_oauth.get_github_client_id.return_value = "Iv1.test"
        mock_oauth.OAuthError = Exception

        # First call raises, second succeeds
        dc = _make_device_code_mock()
        mock_oauth.request_github_device_code.side_effect = [
            Exception("HTTP 530"),
            dc,
        ]

        token = MagicMock()
        token.access_token = "ghp_ok"
        mock_oauth.poll_github_access_token.return_value = token
        mock_wb.open.return_value = True

        # Recovery prompt returns "retry"
        mock_inq.select.return_value.execute.return_value = _RECOVER_RETRY

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        self.assertEqual(config["github_token"], "ghp_ok")
        self.assertEqual(mock_oauth.request_github_device_code.call_count, 2)

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_manual_fallback(self, mock_inq, mock_oauth):
        """User chooses 'Enter manually' after failure."""
        from configurator.cli import _ask_github_token_oauth, _RECOVER_MANUAL

        mock_oauth.get_github_client_id.return_value = "Iv1.test"
        mock_oauth.OAuthError = Exception
        mock_oauth.request_github_device_code.side_effect = Exception("fail")

        # Recovery → manual; then secret prompt returns a token
        mock_inq.select.return_value.execute.return_value = _RECOVER_MANUAL
        mock_inq.secret.return_value.execute.return_value = "ghp_manual"

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        self.assertEqual(config["github_token"], "ghp_manual")

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_skip(self, mock_inq, mock_oauth):
        """User chooses Skip — config should NOT contain github_token."""
        from configurator.cli import _ask_github_token_oauth, _RECOVER_SKIP

        mock_oauth.get_github_client_id.return_value = "Iv1.test"
        mock_oauth.OAuthError = Exception
        mock_oauth.request_github_device_code.side_effect = Exception("fail")

        mock_inq.select.return_value.execute.return_value = _RECOVER_SKIP

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        self.assertNotIn("github_token", config)

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_poll_failure_retry_then_success(self, mock_inq, mock_oauth, mock_wb):
        """Poll failure followed by retry that succeeds."""
        from configurator.cli import _ask_github_token_oauth, _RECOVER_RETRY

        mock_oauth.get_github_client_id.return_value = "Iv1.test"
        mock_oauth.OAuthError = Exception

        dc = _make_device_code_mock()
        mock_oauth.request_github_device_code.return_value = dc

        token = MagicMock()
        token.access_token = "ghp_ok"
        mock_oauth.poll_github_access_token.side_effect = [
            Exception("expired"),
            token,
        ]
        mock_wb.open.return_value = True

        mock_inq.select.return_value.execute.return_value = _RECOVER_RETRY

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_github_token_oauth(config)

        self.assertEqual(config["github_token"], "ghp_ok")


class TestCodexOpenAIOAuthRetrySkip(unittest.TestCase):
    """Verify retry / manual / skip for the OpenAI Device Flow."""

    @staticmethod
    def _make_openai_dc():
        dc = MagicMock()
        dc.device_auth_id = "daid_test"
        dc.user_code = "ABCD-1234"
        dc.verification_uri = "https://auth.openai.com/codex/device"
        dc.interval = 5
        dc.expires_in = 900
        return dc

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_skip(self, mock_inq, mock_oauth):
        """User skips after OpenAI failure — no key written."""
        from configurator.cli import _ask_codex_openai_oauth, _RECOVER_SKIP

        mock_oauth.OAuthError = Exception
        mock_oauth.request_openai_device_code.side_effect = Exception("530")
        mock_inq.select.return_value.execute.return_value = _RECOVER_SKIP

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_codex_openai_oauth(config)

        self.assertNotIn("openai_api_key", config)
        self.assertNotIn("codex_openai_auth_code", config)

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_manual_fallback(self, mock_inq, mock_oauth):
        """User enters API key manually after failure."""
        from configurator.cli import _ask_codex_openai_oauth, _RECOVER_MANUAL

        mock_oauth.OAuthError = Exception
        mock_oauth.request_openai_device_code.side_effect = Exception("530")
        mock_inq.select.return_value.execute.return_value = _RECOVER_MANUAL
        mock_inq.secret.return_value.execute.return_value = "sk-test"

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_codex_openai_oauth(config)

        self.assertEqual(config["openai_api_key"], "sk-test")

    @patch("configurator.cli.webbrowser")
    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_retry_then_success(self, mock_inq, mock_oauth, mock_wb):
        """Retry succeeds on second attempt."""
        from configurator.cli import _ask_codex_openai_oauth, _RECOVER_RETRY

        mock_oauth.OAuthError = Exception
        dc = self._make_openai_dc()
        mock_oauth.request_openai_device_code.side_effect = [Exception("530"), dc]

        token = MagicMock()
        token.access_token = "openai_ok"
        mock_oauth.poll_openai_device_token.return_value = token
        mock_wb.open.return_value = True

        mock_inq.select.return_value.execute.return_value = _RECOVER_RETRY

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            _ask_codex_openai_oauth(config)

        self.assertEqual(config["codex_openai_auth_code"], "openai_ok")


# ---------------------------------------------------------------------------
# Token / key auto-reuse across agents
# ---------------------------------------------------------------------------

class TestTokenAutoReuse(unittest.TestCase):
    """Ensure tokens obtained once are automatically reused later."""

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_github_token_reused_for_codex_oauth(self, mock_inq, mock_oauth):
        """When github_token exists, Codex CLI GitHub OAuth reuses it."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        # Simulate: Copilot + Codex enabled; Copilot already set token
        mock_inq.checkbox.return_value.execute.return_value = ["copilot", "codex"]

        # Copilot auth → OAuth flow → token obtained
        mock_inq.select.return_value.execute.side_effect = [
            "oauth",   # Copilot: "Login via GitHub OAuth"
            "oauth",   # Codex: "Login via GitHub OAuth"
        ]

        # Provide a pre-existing token to skip re-prompting
        config: dict = {"github_token": "ghp_existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            # Copilot OAuth would be called, but token already exists
            # so the function should only display reuse messages
            with patch("configurator.cli._ask_github_token_oauth") as mock_gh:
                _ask_agents(config)

        # _ask_github_token_oauth should NOT be called — token exists
        mock_gh.assert_not_called()

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_github_token_reused_for_opencode_zen(self, mock_inq, mock_oauth):
        """OpenCode Zen/Go auto-reuses an existing GitHub token."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        # First checkbox → agent selection; second checkbox → provider selection
        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],        # agents
            ["opencode-zen"],    # providers
        ]

        config: dict = {"github_token": "ghp_existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("configurator.cli._ask_github_token_oauth") as mock_gh:
                _ask_agents(config)

        # Should reuse, not prompt
        mock_gh.assert_not_called()
        self.assertIn("Reusing", out.getvalue())

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_github_token_reused_for_opencode_copilot(self, mock_inq, mock_oauth):
        """OpenCode github-copilot auto-reuses an existing GitHub token."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],
            ["github-copilot"],
        ]

        config: dict = {"github_token": "ghp_existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("configurator.cli._ask_github_token_oauth") as mock_gh:
                _ask_agents(config)

        mock_gh.assert_not_called()
        self.assertIn("Reusing", out.getvalue())

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_openai_key_reused_for_opencode(self, mock_inq, mock_oauth):
        """OpenCode openai provider auto-reuses an existing OpenAI key."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],
            ["openai"],
        ]

        config: dict = {"openai_api_key": "sk-existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            _ask_agents(config)

        self.assertIn("Reusing", out.getvalue())
        # Key should remain unchanged
        self.assertEqual(config["openai_api_key"], "sk-existing")

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_multiple_opencode_providers(self, mock_inq, mock_oauth):
        """Multiple OpenCode providers selected — credentials collected for all."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],                          # agents
            ["opencode-zen", "openai", "google"],  # providers
        ]
        mock_inq.secret.return_value.execute.return_value = "sk-test-key"

        config: dict = {"github_token": "ghp_existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            _ask_agents(config)

        # Provider stored as comma-separated string
        self.assertEqual(config["opencode_provider"], "opencode-zen,openai,google")
        # GitHub token reused for zen, secrets prompted for openai + google
        self.assertIn("Reusing", out.getvalue())

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_empty_opencode_selection_defaults_to_zen(self, mock_inq, mock_oauth):
        """No provider selected → defaults to opencode-zen."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception

        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],  # agents
            [],            # no providers → default
        ]
        mock_inq.select.return_value.execute.return_value = "oauth"

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            with patch("configurator.cli._ask_github_token_oauth"):
                _ask_agents(config)

        self.assertEqual(config["opencode_provider"], "opencode-zen")

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_claude_key_reused_when_imported(self, mock_inq, mock_oauth):
        """When anthropic_api_key is already imported, Claude step skips prompting."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception
        mock_inq.checkbox.return_value.execute.return_value = ["claude"]

        config: dict = {"anthropic_api_key": "sk-ant-existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            _ask_agents(config)

        mock_inq.secret.assert_not_called()
        self.assertIn("Reusing", out.getvalue())
        self.assertEqual(config["anthropic_api_key"], "sk-ant-existing")

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_gemini_key_reused_when_imported(self, mock_inq, mock_oauth):
        """When google_api_key is already imported, Gemini step skips prompting."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception
        mock_inq.checkbox.return_value.execute.return_value = ["gemini"]

        config: dict = {"google_api_key": "AIza-existing"}
        with patch("sys.stdout", new_callable=StringIO) as out:
            _ask_agents(config)

        mock_inq.secret.assert_not_called()
        self.assertIn("Reusing", out.getvalue())
        self.assertEqual(config["google_api_key"], "AIza-existing")

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_opencode_providers_preselected_from_import(self, mock_inq, mock_oauth):
        """Imported opencode_provider values are pre-selected in the provider checkbox."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception
        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],                              # agent selection
            ["opencode-zen", "github-copilot"],        # provider selection
        ]

        config: dict = {
            "opencode_provider": "opencode-zen,github-copilot",
            "github_token": "ghp_existing",
        }
        with patch("sys.stdout", new_callable=StringIO):
            _ask_agents(config)

        # The second checkbox call (provider selection) must pass the imported
        # providers as defaults so they are pre-ticked in the UI.
        provider_call_kwargs = mock_inq.checkbox.call_args_list[1].kwargs
        self.assertIn("default", provider_call_kwargs)
        self.assertIn("opencode-zen", provider_call_kwargs["default"])
        self.assertIn("github-copilot", provider_call_kwargs["default"])

    @patch("configurator.cli.oauth")
    @patch("configurator.cli.inquirer")
    def test_opencode_providers_no_default_when_not_imported(self, mock_inq, mock_oauth):
        """When opencode_provider is not in config, no default is pre-selected."""
        from configurator.cli import _ask_agents

        mock_oauth.OAuthError = Exception
        mock_inq.checkbox.return_value.execute.side_effect = [
            ["opencode"],        # agent selection
            ["opencode-zen"],    # provider selection (user chose manually)
        ]
        mock_inq.select.return_value.execute.return_value = "manual"

        config: dict = {}
        with patch("sys.stdout", new_callable=StringIO):
            with patch("configurator.cli._ask_github_token_oauth"):
                _ask_agents(config)

        # Second checkbox call: default should be None (no imported value)
        provider_call_kwargs = mock_inq.checkbox.call_args_list[1].kwargs
        self.assertIsNone(provider_call_kwargs.get("default"))


if __name__ == "__main__":
    unittest.main()
