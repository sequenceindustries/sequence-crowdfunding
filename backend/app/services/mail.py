from flask import current_app

from ..extensions import db
from ..models import EmailOutbox


def send_mail(to_email: str, subject: str, body: str):
    """Queue an email. The caller commits. Only the dev outbox exists until a provider is chosen."""
    provider = current_app.config["MAIL_PROVIDER"]
    if provider == "outbox":
        db.session.add(EmailOutbox(to_email=to_email, subject=subject[:300], body=body))
        # Subject only: bodies contain single-use links and must not reach the logs.
        current_app.logger.info("mail queued to outbox: %s", subject)
        return
    raise RuntimeError(f"Unknown mail provider '{provider}'.")
