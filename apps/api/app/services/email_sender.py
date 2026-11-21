"""Email to clients. "outbox" writes .eml files for development, "smtp" sends, "disabled" refuses."""

from __future__ import annotations

import asyncio
import html
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import Settings
from app.core.time import utcnow


class EmailError(RuntimeError):
    """The message was not sent. The text is safe to show the office."""


def build_message(
    settings: Settings, *, to: str, office: str, subject: str, text: str, url: str, button: str
) -> EmailMessage:
    address = settings.email_from or "no-reply@docketflow.local"
    message = EmailMessage()
    message["From"] = formataddr((office, address))
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=address.partition("@")[2] or None)
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(text)
    paragraphs = "".join(
        f"<p style='margin:0 0 12px'>{html.escape(line)}</p>" for line in text.split("\n") if line and line != url
    )
    message.add_alternative(
        "<!doctype html><html lang='he' dir='rtl'><body style='font-family:Arial,sans-serif;color:#1b1a17;"
        "background:#f6f6f3;padding:24px'><div style='max-width:520px;margin:auto;background:#fff;border:1px solid "
        f"#e4e2dc;border-radius:12px;padding:24px'>{paragraphs}<p style='margin:20px 0'><a href='{html.escape(url)}' "
        "style='background:#0e4f49;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;"
        f"font-weight:bold'>{html.escape(button)}</a></p><p style='color:#67625a;font-size:12px' dir='ltr'>"
        f"{html.escape(url)}</p></div></body></html>",
        subtype="html",
    )
    return message


class EmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def available(self) -> bool:
        if self.settings.email_backend == "smtp":
            return bool(self.settings.smtp_host and self.settings.email_from)
        if self.settings.email_backend == "ses":
            return bool(self.settings.email_from)
        return self.settings.email_backend == "outbox"

    async def send(self, message: EmailMessage) -> None:
        backend = self.settings.email_backend
        if backend == "disabled" or not self.available:
            raise EmailError("שליחת אימייל לא הוגדרה בשרת.")
        if backend == "outbox":
            await asyncio.to_thread(self._write_outbox, message)
            return
        if backend == "ses":
            from botocore.exceptions import BotoCoreError, ClientError

            try:
                await asyncio.to_thread(self._send_ses, message)
            except (BotoCoreError, ClientError) as exc:
                raise EmailError("שרת הדואר לא קיבל את ההודעה. נסו שוב מאוחר יותר.") from exc
            return
        try:
            await asyncio.to_thread(self._send_smtp, message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailError("שרת הדואר לא קיבל את ההודעה. נסו שוב מאוחר יותר.") from exc

    def _write_outbox(self, message: EmailMessage) -> None:
        folder = self.settings.resolved_outbox_dir
        folder.mkdir(parents=True, exist_ok=True)
        # Microseconds keep the files in the order they were written when two leave in the same second.
        name = f"{utcnow():%Y%m%dT%H%M%S%f}-{uuid.uuid4().hex[:8]}.eml"
        (folder / name).write_bytes(bytes(message))

    def _send_ses(self, message: EmailMessage) -> None:
        import boto3

        client = boto3.client("sesv2", region_name=self.settings.resolved_ses_region)
        request: dict = {
            "FromEmailAddress": self.settings.email_from,
            "Destination": {"ToAddresses": [str(message["To"])]},
            "Content": {"Raw": {"Data": bytes(message)}},
        }
        if self.settings.ses_configuration_set:
            request["ConfigurationSetName"] = self.settings.ses_configuration_set
        client.send_email(**request)

    def _send_smtp(self, message: EmailMessage) -> None:
        settings = self.settings
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds, context=context
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
        with client:
            if settings.smtp_security == "starttls":
                client.starttls(context=context)
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
