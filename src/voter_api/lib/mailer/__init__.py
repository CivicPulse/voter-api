"""Mailer library — async email delivery via Mailgun.

Public API:
    MailgunMailer: async email sender with Jinja2 template rendering.
    MailDeliveryError: raised on non-2xx Mailgun response.
"""

from voter_api.lib.mailer.mailer import MailDeliveryError, MailgunMailer

__all__ = ["MailDeliveryError", "MailgunMailer"]
