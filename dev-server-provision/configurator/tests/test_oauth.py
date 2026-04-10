"""Tests for the oauth module."""

import unittest
from unittest.mock import patch

from configurator.oauth import (
    DeviceCodeResponse,
    OAuthError,
    OAuthHTTPError,
    OAuthToken,
    OpenAIDeviceCodeResponse,
    build_authorization_url,
    build_google_authorization_url,
    exchange_authorization_code,
    exchange_google_authorization_code,
    extract_code_from_callback_url,
    get_anthropic_client_id,
    get_github_client_id,
    get_google_client_id,
    get_google_client_secret,
    get_openai_client_id,
    get_openai_codex_client_id,
    poll_github_access_token,
    poll_openai_device_token,
    request_github_device_code,
    request_openai_device_code,
)


# ---------------------------------------------------------------------------
# get_github_client_id
# ---------------------------------------------------------------------------

class TestGetGithubClientId(unittest.TestCase):
    def test_returns_builtin_by_default(self):
        """Without env var, the built-in constant is returned."""
        with patch.dict("os.environ", {}, clear=False):
            # Remove env var if present
            import os
            os.environ.pop("GITHUB_OAUTH_CLIENT_ID", None)
            cid = get_github_client_id()
        self.assertEqual(cid, "Ov23liu7cPhVnaUoWhUl")

    def test_env_var_overrides_builtin(self):
        """GITHUB_OAUTH_CLIENT_ID env var takes precedence."""
        with patch.dict("os.environ", {"GITHUB_OAUTH_CLIENT_ID": "Iv1.custom_id"}):
            cid = get_github_client_id()
        self.assertEqual(cid, "Iv1.custom_id")

    def test_env_var_whitespace_stripped(self):
        """Leading/trailing whitespace in env var is stripped."""
        with patch.dict("os.environ", {"GITHUB_OAUTH_CLIENT_ID": "  Iv1.spaced  "}):
            cid = get_github_client_id()
        self.assertEqual(cid, "Iv1.spaced")

    def test_empty_env_var_falls_back_to_builtin(self):
        """An empty env var should fall back to the built-in constant."""
        with patch.dict("os.environ", {"GITHUB_OAUTH_CLIENT_ID": ""}):
            cid = get_github_client_id()
        self.assertEqual(cid, "Ov23liu7cPhVnaUoWhUl")

    def test_whitespace_only_env_var_falls_back(self):
        """A whitespace-only env var should fall back to the built-in constant."""
        with patch.dict("os.environ", {"GITHUB_OAUTH_CLIENT_ID": "   "}):
            cid = get_github_client_id()
        self.assertEqual(cid, "Ov23liu7cPhVnaUoWhUl")


# ---------------------------------------------------------------------------
# get_google_client_id / get_google_client_secret
# ---------------------------------------------------------------------------

class TestGetGoogleClientId(unittest.TestCase):
    def test_returns_empty_by_default(self):
        """No built-in Google Client ID — returns empty string."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
            cid = get_google_client_id()
        self.assertEqual(cid, "")

    def test_env_var_overrides(self):
        with patch.dict("os.environ", {"GOOGLE_OAUTH_CLIENT_ID": "123.apps.googleusercontent.com"}):
            cid = get_google_client_id()
        self.assertEqual(cid, "123.apps.googleusercontent.com")

    def test_whitespace_stripped(self):
        with patch.dict("os.environ", {"GOOGLE_OAUTH_CLIENT_ID": "  gid  "}):
            self.assertEqual(get_google_client_id(), "gid")

    def test_whitespace_only_env_var_returns_empty(self):
        """A whitespace-only env var should return empty (no built-in)."""
        with patch.dict("os.environ", {"GOOGLE_OAUTH_CLIENT_ID": "   "}):
            self.assertEqual(get_google_client_id(), "")


class TestGetGoogleClientSecret(unittest.TestCase):
    def test_returns_empty_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)
            secret = get_google_client_secret()
        self.assertEqual(secret, "")

    def test_env_var_overrides(self):
        with patch.dict("os.environ", {"GOOGLE_OAUTH_CLIENT_SECRET": "GOCSPX-test"}):
            self.assertEqual(get_google_client_secret(), "GOCSPX-test")


# ---------------------------------------------------------------------------
# get_anthropic_client_id
# ---------------------------------------------------------------------------

class TestGetAnthropicClientId(unittest.TestCase):
    def test_returns_empty_by_default(self):
        """Anthropic uses API keys, not OAuth — returns empty string."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ANTHROPIC_OAUTH_CLIENT_ID", None)
            cid = get_anthropic_client_id()
        self.assertEqual(cid, "")

    def test_env_var_overrides(self):
        """If Anthropic adds OAuth in the future, env var should work."""
        with patch.dict("os.environ", {"ANTHROPIC_OAUTH_CLIENT_ID": "ant_future"}):
            self.assertEqual(get_anthropic_client_id(), "ant_future")


# ---------------------------------------------------------------------------
# get_openai_client_id
# ---------------------------------------------------------------------------

class TestGetOpenaiClientId(unittest.TestCase):
    def test_returns_empty_by_default(self):
        """OpenAI/Codex CLI uses GitHub OAuth or API key — returns empty string."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OPENAI_OAUTH_CLIENT_ID", None)
            cid = get_openai_client_id()
        self.assertEqual(cid, "")

    def test_env_var_overrides(self):
        """If OpenAI adds OAuth in the future, env var should work."""
        with patch.dict("os.environ", {"OPENAI_OAUTH_CLIENT_ID": "oai_future"}):
            self.assertEqual(get_openai_client_id(), "oai_future")


# ---------------------------------------------------------------------------
# build_google_authorization_url
# ---------------------------------------------------------------------------

class TestBuildGoogleAuthorizationUrl(unittest.TestCase):
    def test_raises_when_no_client_id(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
            with self.assertRaises(OAuthError) as ctx:
                build_google_authorization_url()
            self.assertIn("No Google OAuth Client ID", str(ctx.exception))

    def test_builds_url_with_env_var(self):
        with patch.dict("os.environ", {"GOOGLE_OAUTH_CLIENT_ID": "123.apps.googleusercontent.com"}):
            url = build_google_authorization_url()
        self.assertIn("accounts.google.com", url)
        self.assertIn("client_id=123.apps.googleusercontent.com", url)
        self.assertIn("redirect_uri=", url)
        self.assertIn("generative-language", url)


# ---------------------------------------------------------------------------
# exchange_google_authorization_code
# ---------------------------------------------------------------------------

class TestExchangeGoogleAuthorizationCode(unittest.TestCase):
    def test_raises_when_no_credentials(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
            os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)
            with self.assertRaises(OAuthError) as ctx:
                exchange_google_authorization_code("some_code")
            self.assertIn("Client ID and Secret are required", str(ctx.exception))

    @patch("configurator.oauth._post_form")
    def test_success_with_credentials(self, mock_post):
        mock_post.return_value = {
            "access_token": "ya29.test",
            "token_type": "Bearer",
        }
        with patch.dict("os.environ", {
            "GOOGLE_OAUTH_CLIENT_ID": "123.apps.googleusercontent.com",
            "GOOGLE_OAUTH_CLIENT_SECRET": "GOCSPX-test",
        }):
            token = exchange_google_authorization_code("auth_code")
        self.assertEqual(token.access_token, "ya29.test")


# ---------------------------------------------------------------------------
# extract_code_from_callback_url
# ---------------------------------------------------------------------------

class TestExtractCodeFromCallbackUrl(unittest.TestCase):
    def test_full_url_with_code(self):
        url = "https://example.com/callback?code=abc123&state=xyz"
        self.assertEqual(extract_code_from_callback_url(url), "abc123")

    def test_bare_code(self):
        self.assertEqual(extract_code_from_callback_url("abc123"), "abc123")

    def test_bare_code_with_spaces(self):
        self.assertEqual(extract_code_from_callback_url("  abc123  "), "abc123")

    def test_empty_raises(self):
        with self.assertRaises(OAuthError):
            extract_code_from_callback_url("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(OAuthError):
            extract_code_from_callback_url("   ")

    def test_url_with_error(self):
        url = "https://example.com/callback?error=access_denied&error_description=User+denied"
        with self.assertRaises(OAuthError) as ctx:
            extract_code_from_callback_url(url)
        self.assertIn("User denied", str(ctx.exception))

    def test_url_without_code_raises(self):
        url = "https://example.com/callback?state=xyz"
        with self.assertRaises(OAuthError):
            extract_code_from_callback_url(url)

    def test_localhost_url(self):
        url = "http://localhost:8080/callback?code=ghp_test123"
        self.assertEqual(extract_code_from_callback_url(url), "ghp_test123")

    def test_url_with_fragment_only(self):
        # URL with query parameter should still work
        url = "https://example.com/callback?code=mycode123"
        self.assertEqual(extract_code_from_callback_url(url), "mycode123")


# ---------------------------------------------------------------------------
# build_authorization_url
# ---------------------------------------------------------------------------

class TestBuildAuthorizationUrl(unittest.TestCase):
    def test_basic(self):
        url = build_authorization_url(
            authorize_url="https://example.com/authorize",
            client_id="my_client",
        )
        self.assertIn("https://example.com/authorize?", url)
        self.assertIn("client_id=my_client", url)
        self.assertIn("response_type=code", url)

    def test_with_all_params(self):
        url = build_authorization_url(
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            client_id="123.apps.googleusercontent.com",
            redirect_uri="http://localhost:8080",
            scope="email profile",
            state="random_state",
        )
        self.assertIn("client_id=123.apps.googleusercontent.com", url)
        self.assertIn("redirect_uri=", url)
        self.assertIn("scope=email+profile", url)
        self.assertIn("state=random_state", url)

    def test_without_optional_params(self):
        url = build_authorization_url(
            authorize_url="https://example.com/auth",
            client_id="test",
        )
        self.assertNotIn("redirect_uri", url)
        self.assertNotIn("scope", url)
        self.assertNotIn("state", url)

    def test_preserves_existing_query_params(self):
        url = build_authorization_url(
            authorize_url="https://example.com/auth?existing=value",
            client_id="test",
        )
        self.assertIn("existing=value", url)
        self.assertIn("client_id=test", url)
        # Should not have double '?'
        self.assertEqual(url.count("?"), 1)


# ---------------------------------------------------------------------------
# DeviceCodeResponse / OAuthToken dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses(unittest.TestCase):
    def test_device_code_response(self):
        dc = DeviceCodeResponse(
            device_code="dc_123",
            user_code="ABCD-1234",
            verification_uri="https://github.com/login/device",
            interval=5,
            expires_in=900,
        )
        self.assertEqual(dc.device_code, "dc_123")
        self.assertEqual(dc.user_code, "ABCD-1234")
        self.assertEqual(dc.verification_uri, "https://github.com/login/device")
        self.assertEqual(dc.interval, 5)
        self.assertEqual(dc.expires_in, 900)
        self.assertEqual(dc.verification_uri_complete, "")

    def test_device_code_response_with_complete_uri(self):
        dc = DeviceCodeResponse(
            device_code="dc_123",
            user_code="ABCD-1234",
            verification_uri="https://github.com/login/device",
            interval=5,
            expires_in=900,
            verification_uri_complete="https://github.com/login/device?user_code=ABCD-1234",
        )
        self.assertEqual(dc.verification_uri_complete, "https://github.com/login/device?user_code=ABCD-1234")

    def test_oauth_token(self):
        token = OAuthToken(access_token="ghp_test123")
        self.assertEqual(token.access_token, "ghp_test123")
        self.assertEqual(token.token_type, "bearer")
        self.assertEqual(token.scope, "")

    def test_oauth_token_with_scope(self):
        token = OAuthToken(access_token="tok", token_type="Bearer", scope="read:user")
        self.assertEqual(token.scope, "read:user")


# ---------------------------------------------------------------------------
# request_github_device_code (mocked HTTP)
# ---------------------------------------------------------------------------

class TestRequestGitHubDeviceCode(unittest.TestCase):
    @patch("configurator.oauth._post_form")
    def test_success(self, mock_post):
        mock_post.return_value = {
            "device_code": "dc_abc",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "interval": "5",
            "expires_in": "900",
        }
        dc = request_github_device_code("client_123")
        self.assertEqual(dc.device_code, "dc_abc")
        self.assertEqual(dc.user_code, "ABCD-1234")
        self.assertEqual(dc.interval, 5)
        self.assertEqual(dc.verification_uri_complete, "")
        mock_post.assert_called_once()

    @patch("configurator.oauth._post_form")
    def test_success_with_complete_uri(self, mock_post):
        mock_post.return_value = {
            "device_code": "dc_abc",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "verification_uri_complete": "https://github.com/login/device?user_code=ABCD-1234",
            "interval": "5",
            "expires_in": "900",
        }
        dc = request_github_device_code("client_123")
        self.assertEqual(dc.verification_uri_complete, "https://github.com/login/device?user_code=ABCD-1234")

    @patch("configurator.oauth._post_form")
    def test_error_response(self, mock_post):
        mock_post.return_value = {
            "error": "unauthorized_client",
            "error_description": "The client is not authorized.",
        }
        with self.assertRaises(OAuthError) as ctx:
            request_github_device_code("bad_client")
        self.assertIn("not authorized", str(ctx.exception))

    @patch("configurator.oauth._post_form")
    def test_network_error(self, mock_post):
        mock_post.side_effect = OAuthError("Network error")
        with self.assertRaises(OAuthError):
            request_github_device_code("client_123")


# ---------------------------------------------------------------------------
# poll_github_access_token (mocked HTTP + time)
# ---------------------------------------------------------------------------

class TestPollGitHubAccessToken(unittest.TestCase):
    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_success_after_pending(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            {"error": "authorization_pending"},
            {"access_token": "ghp_final", "token_type": "bearer", "scope": "read:user"},
        ]
        token = poll_github_access_token("cid", "dc", interval=1, expires_in=30)
        self.assertEqual(token.access_token, "ghp_final")
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_access_denied(self, mock_post, mock_sleep):
        mock_post.return_value = {"error": "access_denied"}
        with self.assertRaises(OAuthError) as ctx:
            poll_github_access_token("cid", "dc", interval=1, expires_in=10)
        self.assertIn("denied", str(ctx.exception))

    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_expired_token(self, mock_post, mock_sleep):
        mock_post.return_value = {"error": "expired_token"}
        with self.assertRaises(OAuthError) as ctx:
            poll_github_access_token("cid", "dc", interval=1, expires_in=10)
        self.assertIn("expired", str(ctx.exception))

    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_slow_down_increases_interval(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            {"error": "slow_down", "interval": "10"},
            {"access_token": "ghp_ok", "token_type": "bearer"},
        ]
        token = poll_github_access_token("cid", "dc", interval=1, expires_in=30)
        self.assertEqual(token.access_token, "ghp_ok")

    @patch("configurator.oauth.time.monotonic")
    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_timeout(self, mock_post, mock_sleep, mock_mono):
        # Simulate time passing beyond the deadline
        mock_mono.side_effect = [0, 1000]
        mock_post.return_value = {"error": "authorization_pending"}
        with self.assertRaises(OAuthError) as ctx:
            poll_github_access_token("cid", "dc", interval=1, expires_in=5)
        self.assertIn("Timed out", str(ctx.exception))

    @patch("configurator.oauth.time.sleep")
    @patch("configurator.oauth._post_form")
    def test_http_error_propagates(self, mock_post, mock_sleep):
        """Non-retryable HTTP errors should propagate immediately."""
        mock_post.side_effect = OAuthError("HTTP 401 from https://github.com/login/oauth/access_token")
        with self.assertRaises(OAuthError) as ctx:
            poll_github_access_token("cid", "dc", interval=1, expires_in=10)
        self.assertIn("HTTP 401", str(ctx.exception))


# ---------------------------------------------------------------------------
# exchange_authorization_code (mocked HTTP)
# ---------------------------------------------------------------------------

class TestExchangeAuthorizationCode(unittest.TestCase):
    @patch("configurator.oauth._post_form")
    def test_success(self, mock_post):
        mock_post.return_value = {
            "access_token": "ya29.test",
            "token_type": "Bearer",
            "scope": "email",
        }
        token = exchange_authorization_code(
            token_url="https://oauth2.googleapis.com/token",
            client_id="cid",
            client_secret="csecret",
            code="auth_code_123",
        )
        self.assertEqual(token.access_token, "ya29.test")
        self.assertEqual(token.token_type, "Bearer")

    @patch("configurator.oauth._post_form")
    def test_error_response(self, mock_post):
        mock_post.return_value = {
            "error": "invalid_grant",
            "error_description": "Code has expired.",
        }
        with self.assertRaises(OAuthError) as ctx:
            exchange_authorization_code(
                token_url="https://oauth2.googleapis.com/token",
                client_id="cid",
                client_secret="csecret",
                code="expired_code",
            )
        self.assertIn("expired", str(ctx.exception))

    @patch("configurator.oauth._post_form")
    def test_no_access_token(self, mock_post):
        mock_post.return_value = {"token_type": "bearer"}
        with self.assertRaises(OAuthError):
            exchange_authorization_code(
                token_url="https://example.com/token",
                client_id="cid",
                client_secret="csecret",
                code="code",
            )

    @patch("configurator.oauth._post_form")
    def test_includes_redirect_uri(self, mock_post):
        mock_post.return_value = {"access_token": "tok", "token_type": "bearer"}
        exchange_authorization_code(
            token_url="https://example.com/token",
            client_id="cid",
            client_secret="csecret",
            code="code",
            redirect_uri="http://localhost:8080",
        )
        call_data = mock_post.call_args[0][1]
        self.assertEqual(call_data["redirect_uri"], "http://localhost:8080")


# ---------------------------------------------------------------------------
# OAuthError
# ---------------------------------------------------------------------------

class TestOAuthError(unittest.TestCase):
    def test_is_exception(self):
        self.assertTrue(issubclass(OAuthError, Exception))

    def test_message(self):
        err = OAuthError("something went wrong")
        self.assertEqual(str(err), "something went wrong")

    def test_http_error_is_subclass(self):
        self.assertTrue(issubclass(OAuthHTTPError, OAuthError))

    def test_http_error_status_code(self):
        err = OAuthHTTPError("HTTP 403", status_code=403)
        self.assertEqual(err.status_code, 403)
        self.assertIn("403", str(err))


# ---------------------------------------------------------------------------
# get_openai_codex_client_id
# ---------------------------------------------------------------------------

class TestGetOpenaiCodexClientId(unittest.TestCase):
    def test_returns_builtin_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OPENAI_CODEX_CLIENT_ID", None)
            cid = get_openai_codex_client_id()
        self.assertEqual(cid, "app_EMoamEEZ73f0CkXaXp7hrann")

    def test_env_var_overrides(self):
        with patch.dict("os.environ", {"OPENAI_CODEX_CLIENT_ID": "custom_app_id"}):
            self.assertEqual(get_openai_codex_client_id(), "custom_app_id")

    def test_strips_whitespace(self):
        with patch.dict("os.environ", {"OPENAI_CODEX_CLIENT_ID": "  custom_app_id  "}):
            self.assertEqual(get_openai_codex_client_id(), "custom_app_id")


# ---------------------------------------------------------------------------
# OpenAIDeviceCodeResponse dataclass
# ---------------------------------------------------------------------------

class TestOpenAIDeviceCodeResponse(unittest.TestCase):
    def test_fields(self):
        resp = OpenAIDeviceCodeResponse(
            device_auth_id="dauth_123",
            user_code="ABCD-1234",
            verification_uri="https://auth.openai.com/codex/device",
            interval=5,
        )
        self.assertEqual(resp.device_auth_id, "dauth_123")
        self.assertEqual(resp.user_code, "ABCD-1234")
        self.assertEqual(resp.verification_uri, "https://auth.openai.com/codex/device")
        self.assertEqual(resp.interval, 5)
        self.assertEqual(resp.expires_in, 900)  # default


if __name__ == "__main__":
    unittest.main()
