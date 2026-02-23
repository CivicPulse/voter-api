"""Unit tests for MailgunMailer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.lib.mailer import MailDeliveryError, MailgunMailer


@pytest.fixture()
def mailer() -> MailgunMailer:
    return MailgunMailer(
        api_key="key-test",
        domain="test.mailgun.org",
        from_email="noreply@test.mailgun.org",
        from_name="Test App",
    )


class TestSendEmail:
    """Tests for MailgunMailer.send_email."""

    async def test_send_email_calls_mailgun_with_correct_payload(self, mailer: MailgunMailer) -> None:
        mock_response = MagicMock(status_code=200)
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.messages = mock_messages

        with patch("voter_api.lib.mailer.mailer.AsyncClient", return_value=mock_client_instance):
            await mailer.send_email("user@example.com", "Test Subject", "<p>Hello</p>")

        mock_messages.create.assert_called_once()
        call_kwargs = mock_messages.create.call_args
        data = call_kwargs.kwargs["data"] if call_kwargs.kwargs else call_kwargs[1]["data"]
        assert data["to"] == "user@example.com"
        assert data["subject"] == "Test Subject"
        assert data["html"] == "<p>Hello</p>"
        assert "Test App" in data["from"]
        assert "noreply@test.mailgun.org" in data["from"]

    async def test_send_email_uses_correct_domain(self, mailer: MailgunMailer) -> None:
        mock_response = MagicMock(status_code=200)
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.messages = mock_messages

        with patch("voter_api.lib.mailer.mailer.AsyncClient", return_value=mock_client_instance):
            await mailer.send_email("user@example.com", "Subject", "<p>body</p>")

        call_kwargs = mock_messages.create.call_args
        domain = call_kwargs.kwargs.get("domain") or call_kwargs[1].get("domain")
        assert domain == "test.mailgun.org"

    async def test_send_email_raises_on_non_2xx_status(self, mailer: MailgunMailer) -> None:
        mock_response = MagicMock(status_code=400)
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.messages = mock_messages

        with (
            patch("voter_api.lib.mailer.mailer.AsyncClient", return_value=mock_client_instance),
            pytest.raises(MailDeliveryError),
        ):
            await mailer.send_email("user@example.com", "Subject", "<p>body</p>")

    async def test_send_email_raises_on_500_status(self, mailer: MailgunMailer) -> None:
        mock_response = MagicMock(status_code=500)
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.messages = mock_messages

        with (
            patch("voter_api.lib.mailer.mailer.AsyncClient", return_value=mock_client_instance),
            pytest.raises(MailDeliveryError),
        ):
            await mailer.send_email("user@example.com", "Subject", "<p>body</p>")

    def test_mail_delivery_error_is_runtime_error(self) -> None:
        assert issubclass(MailDeliveryError, RuntimeError)


class TestRenderTemplate:
    """Tests for MailgunMailer.render_template."""

    def test_render_password_reset_template(self, mailer: MailgunMailer) -> None:
        html = mailer.render_template(
            "password_reset.html",
            {"app_name": "Voter API", "reset_url": "https://example.com/reset?token=abc123"},
        )
        assert "abc123" in html
        assert "Voter API" in html
        assert "24 hours" in html

    def test_render_invite_template(self, mailer: MailgunMailer) -> None:
        html = mailer.render_template(
            "invite.html",
            {
                "app_name": "Voter API",
                "invite_url": "https://example.com/invite?token=xyz",
                "role": "analyst",
            },
        )
        assert "analyst" in html
        assert "Voter API" in html
        assert "7 days" in html
        assert "xyz" in html

    def test_render_template_escapes_html(self, mailer: MailgunMailer) -> None:
        html = mailer.render_template(
            "invite.html",
            {
                "app_name": "<script>alert(1)</script>",
                "invite_url": "https://example.com",
                "role": "viewer",
            },
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
