"""Mailgun-based async email delivery with Jinja2 template rendering."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from mailgun.client import AsyncClient  # type: ignore[import-untyped]

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)


class MailDeliveryError(RuntimeError):
    """Raised when Mailgun returns a non-2xx response."""


class MailgunMailer:
    """Async email sender via the official Mailgun Python SDK.

    Args:
        api_key: Mailgun API key.
        domain: Mailgun sending domain.
        from_email: Sender email address.
        from_name: Sender display name.
    """

    def __init__(self, api_key: str, domain: str, from_email: str, from_name: str = "Voter API") -> None:
        self._api_key = api_key
        self._domain = domain
        self._from_email = from_email
        self._from_name = from_name

    async def send_email(self, to: str, subject: str, html_body: str) -> None:
        """Send an HTML email via Mailgun.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html_body: Rendered HTML body.

        Raises:
            MailDeliveryError: If Mailgun returns a non-2xx response.
        """
        from_address = f"{self._from_name} <{self._from_email}>"
        async with AsyncClient(auth=("api", self._api_key)) as client:
            response = await client.messages.create(
                data={
                    "from": from_address,
                    "to": to,
                    "subject": subject,
                    "html": html_body,
                },
                domain=self._domain,
            )
        status = getattr(response, "status_code", None) or getattr(response, "status", None)
        if status is None:
            msg = "Mailgun response missing status code"
            raise MailDeliveryError(msg)
        if status < 200 or status >= 300:
            msg = f"Mailgun delivery failed with status {status}"
            raise MailDeliveryError(msg)

    def render_template(self, name: str, context: dict) -> str:
        """Render a Jinja2 HTML email template.

        Args:
            name: Template filename (e.g. 'password_reset.html').
            context: Template context variables.

        Returns:
            Rendered HTML string.
        """
        template = _jinja_env.get_template(name)
        return template.render(**context)

    async def send_template(self, to: str, subject: str, template_name: str, context: dict) -> None:
        """Render a template and send the resulting email.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            template_name: Template filename under lib/mailer/templates/.
            context: Template context variables.

        Raises:
            MailDeliveryError: If Mailgun returns a non-2xx response.
        """
        html_body = self.render_template(template_name, context)
        await self.send_email(to, subject, html_body)
