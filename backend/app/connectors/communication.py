"""Azure Communication Services connection for customer notifications
(email + SMS). Auth uses the resource's connection string directly (ACS
doesn't support Azure AD auth for these two clients the way Foundry/Key
Vault do), loaded from settings the same way every other secret here is.

Both send_email() and send_sms() return a plain bool rather than raising -
a notification failure should never break claim submission or a decision
being recorded, it should just be visible (via the Notification row's
status) rather than crash the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from azure.communication.email import EmailClient
    from azure.communication.sms import SmsClient

_email_client: "EmailClient | None" = None
_sms_client: "SmsClient | None" = None


def email_configured() -> bool:
    return bool(settings.azure_communication_connection_string and settings.azure_communication_email_sender)


def sms_configured() -> bool:
    return bool(settings.azure_communication_connection_string and settings.azure_communication_sms_sender)


def get_email_client() -> "EmailClient":
    global _email_client
    if _email_client is None:
        from azure.communication.email import EmailClient

        _email_client = EmailClient.from_connection_string(settings.azure_communication_connection_string)
    return _email_client


def get_sms_client() -> "SmsClient":
    global _sms_client
    if _sms_client is None:
        from azure.communication.sms import SmsClient

        _sms_client = SmsClient.from_connection_string(settings.azure_communication_connection_string)
    return _sms_client


def send_email(to: str, subject: str, body: str) -> bool:
    """Blocking call - callers from async code should wrap this in
    asyncio.to_thread, same pattern as every other external API call in
    this codebase."""
    if not email_configured():
        return False
    try:
        message = {
            "senderAddress": settings.azure_communication_email_sender,
            "recipients": {"to": [{"address": to}]},
            "content": {"subject": subject, "plainText": body},
        }
        poller = get_email_client().begin_send(message)
        result = poller.result()
        return str(result.get("status", "")).lower() == "succeeded"
    except Exception:
        return False


def send_sms(to: str, message: str) -> bool:
    """Blocking call - same asyncio.to_thread requirement as send_email()."""
    if not sms_configured():
        return False
    try:
        results = get_sms_client().send(
            from_=settings.azure_communication_sms_sender,
            to=[to],
            message=message,
        )
        return bool(results) and all(r.successful for r in results)
    except Exception:
        return False


def reset_communication_clients() -> None:
    """Clear cached clients (useful in tests)."""
    global _email_client, _sms_client
    _email_client = None
    _sms_client = None
