"""Minimal SMTP email sending -- the one primitive every branded email in
this project (password reset, OTP codes, cashback credited, order/redemption
notifications, ...) is built on top of, via core/email_templates.py::
render_email() for the HTML body.

No email infrastructure existed anywhere in this project before this. Rather
than fake it or block the whole password-reset feature on procuring an SMTP
provider, this sends for real when SMTP_HOST is configured, and otherwise
writes the would-be email (including the reset link) to the audit log --
real, inspectable, and never silently lost, but not actually delivered until
SMTP is configured (see docs/business-rules.md §Password reset)."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class EmailNotConfiguredError(Exception):
    pass


#: Il dominio degli atleti senza email: `.invalid` è riservato (RFC 2606),
#: nessuna posta può arrivarci.
PLACEHOLDER_EMAIL_DOMAIN = "atleta.invalid"


def is_placeholder_address(address: str | None) -> bool:
    return (address or "").lower().endswith(f"@{PLACEHOLDER_EMAIL_DOMAIN}")


def send_html_email(
    *, to: str, subject: str, html_body: str, text_body: str,
    from_address: str | None = None, reply_to: str | None = None, bcc: str | None = None,
) -> None:
    """Same delivery mechanics as send_email(), but multipart/alternative: a
    plain-text fallback (required -- some clients/spam filters penalize
    HTML-only mail) alongside the real, branded HTML body built via
    core/email_templates.py.

    `from_address`, `reply_to` e `bcc` servono alle email che non sono
    notifiche del sistema ma lettere a terzi (l'ordine al fornitore, la
    richiesta di trasporto al comune): partono da info@, la risposta torna a
    chi le ha scritte e una copia resta nella casella che le manda. Il server
    SMTP deve accettare `from_address` come mittente."""
    if not settings.smtp_host:
        raise EmailNotConfiguredError("SMTP is not configured (smtp_host is empty)")
    if is_placeholder_address(to):
        # L'account di un atleta senza email (club/athlete_access.py): non c'è
        # nessuno a cui scrivere, e non è un errore.
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address or settings.smtp_from_address
    message["To"] = to
    if reply_to:
        message["Reply-To"] = reply_to
    if bcc:
        message["Bcc"] = bcc
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def send_html_email_best_effort(
    *, context: str, to: str, subject: str, html_body: str, text_body: str,
    from_address: str | None = None, reply_to: str | None = None, bcc: str | None = None,
) -> bool:
    """For notification mail that is sent AFTER the work it announces is
    already committed -- an order marked paid, a wallet credited, a ticket
    opened, an account invited.

    Every one of those call sites used to catch only `EmailNotConfiguredError`,
    which covers exactly one of the many ways a real mail server fails. A
    refused login, a timeout (send_html_email opens a blocking 10-second
    smtplib connection to an external host), a DNS blip or a TLS error all
    escaped instead, turning into a 500 on an operation that had ALREADY
    succeeded and been audited. The worst case was the admin wallet top-up:
    the money was credited, the admin saw "Si è verificato un errore
    imprevisto", clicked again -- and, because the browser mints a fresh
    idempotency key per click, credited the wallet a second time.

    So: the transaction is the deliverable, the email is a courtesy. This
    never raises. It returns whether the mail actually went out, for the rare
    caller that wants to say so.

    Deliberately NOT used for password-reset links and OTP codes: there the
    email IS the deliverable, and failing loudly is the correct behaviour."""
    try:
        send_html_email(
            to=to, subject=subject, html_body=html_body, text_body=text_body,
            from_address=from_address, reply_to=reply_to, bcc=bcc,
        )
        return True
    except EmailNotConfiguredError:
        logger.warning("%s: email to %s not sent (SMTP not configured)", context, to)
        return False
    except Exception:
        logger.exception("%s: email to %s failed", context, to)
        return False
