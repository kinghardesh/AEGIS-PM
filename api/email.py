"""
aegis-pm / api / email.py

Outbound email.

Backends
────────
  EMAIL_BACKEND=console   (default)   logs to stdout — dev only
  EMAIL_BACKEND=smtp                  real SMTP over TLS

SMTP env vars
─────────────
  SMTP_HOST          e.g. smtp.gmail.com, email-smtp.us-east-1.amazonaws.com
  SMTP_PORT          587 (STARTTLS) or 465 (implicit TLS)
  SMTP_USER          login
  SMTP_PASSWORD      app password / API secret
  SMTP_FROM          "Aegis PM <noreply@yourdomain.com>"
  SMTP_USE_TLS       starttls (default) | ssl | none
  SMTP_TIMEOUT       seconds, default 15

Design notes
────────────
  - Sends run in a worker thread via asyncio.to_thread so the event loop
    never blocks on SMTP negotiation.
  - Uses email.message.EmailMessage (modern stdlib API) — correct headers,
    UTF-8 encoding, and Message-ID generation come for free.
  - Never logs message bodies (they carry reset links / secrets).
  - Failures raise up to the caller; the /auth/forgot-password endpoint
    already swallows + logs them so user-enumeration isn't possible via
    a differing response.
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MIMEEmailMessage
from email.utils import formatdate, make_msgid

log = logging.getLogger("aegis.email")


@dataclass
class EmailMessage:
    to:      str
    subject: str
    body:    str


# ── Backend interface ────────────────────────────────────────────────────────

class EmailSender:
    async def send(self, msg: EmailMessage) -> None:  # pragma: no cover
        raise NotImplementedError


# ── Console backend (dev) ────────────────────────────────────────────────────

class ConsoleEmailSender(EmailSender):
    """Dev / test backend. Logs the email to stdout. Never use in prod."""

    async def send(self, msg: EmailMessage) -> None:
        log.info(
            "\n────── EMAIL (console backend) ──────\n"
            "To:      %s\n"
            "Subject: %s\n\n"
            "%s\n"
            "─────────────────────────────────────\n",
            msg.to, msg.subject, msg.body,
        )


# ── SMTP backend (prod) ──────────────────────────────────────────────────────

class SmtpEmailSender(EmailSender):
    """
    TLS-first SMTP sender. Keeps one config per process, no connection
    pooling — fine for low-volume transactional email (password resets,
    notifications). For high volume, swap in a hosted provider's HTTP API.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        use_tls: str = "starttls",
        timeout: float = 15.0,
    ) -> None:
        self.host      = host
        self.port      = port
        self.user      = user
        self.password  = password
        self.from_addr = from_addr
        self.use_tls   = use_tls.lower()
        self.timeout   = timeout
        if self.use_tls not in {"starttls", "ssl", "none"}:
            raise ValueError(f"SMTP_USE_TLS must be starttls|ssl|none, got {use_tls!r}")

    def _build(self, msg: EmailMessage) -> MIMEEmailMessage:
        mime = MIMEEmailMessage()
        mime["From"]       = self.from_addr
        mime["To"]         = msg.to
        mime["Subject"]    = msg.subject
        mime["Date"]       = formatdate(localtime=True)
        mime["Message-ID"] = make_msgid(domain=self.host)
        mime.set_content(msg.body, subtype="plain", charset="utf-8")
        return mime

    def _send_sync(self, mime: MIMEEmailMessage) -> None:
        context = ssl.create_default_context()
        if self.use_tls == "ssl":
            with smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout, context=context
            ) as s:
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(mime)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                s.ehlo()
                if self.use_tls == "starttls":
                    s.starttls(context=context)
                    s.ehlo()
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(mime)

    async def send(self, msg: EmailMessage) -> None:
        mime = self._build(msg)
        # Don't log the body — it carries secrets (reset links).
        log.info("smtp send to=%s subject=%r", msg.to, msg.subject)
        try:
            await asyncio.to_thread(self._send_sync, mime)
        except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
            # Leak class only, never the message content.
            log.error("smtp send failed to=%s: %s: %s", msg.to, type(e).__name__, e)
            raise


# ── Factory ──────────────────────────────────────────────────────────────────

def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"[email] EMAIL_BACKEND=smtp requires {name}. "
            f"See .env.example for the full SMTP block."
        )
    return val


def get_sender() -> EmailSender:
    backend = os.getenv("EMAIL_BACKEND", "console").lower()
    if backend == "console":
        return ConsoleEmailSender()
    if backend == "smtp":
        return SmtpEmailSender(
            host      = _require("SMTP_HOST"),
            port      = int(os.getenv("SMTP_PORT", "587")),
            user      = os.getenv("SMTP_USER", "").strip(),
            password  = os.getenv("SMTP_PASSWORD", ""),
            from_addr = _require("SMTP_FROM"),
            use_tls   = os.getenv("SMTP_USE_TLS", "starttls"),
            timeout   = float(os.getenv("SMTP_TIMEOUT", "15")),
        )
    raise RuntimeError(f"Unknown EMAIL_BACKEND={backend!r}. Use 'console' or 'smtp'.")
