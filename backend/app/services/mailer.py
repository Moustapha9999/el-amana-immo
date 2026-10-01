"""Envoi d'e-mails transactionnels (SMTP, bibliothèque standard).

Inactif tant que SMTP_HOST n'est pas renseigné : les appelants gardent la
notification in-app comme canal principal.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def mail_enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_host and (s.smtp_from or s.smtp_user))


def _send_sync(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("envoi e-mail échoué vers %s : %s", to, type(exc).__name__)
        return False


async def send_mail(to: str | None, subject: str, body: str) -> bool:
    if not to or not mail_enabled():
        return False
    return await asyncio.to_thread(_send_sync, to, subject, body)
