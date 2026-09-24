"""Customer notifications - email/SMS via Azure Communication Services, at
the points in a claim's life where the customer actually needs to hear
something: submission, and whatever Generation decides (approved/declined/
under review).

Never raises into the caller. A failed or unconfigured send doesn't stop a
claim being submitted or a decision being recorded - it's recorded as a
"failed" Notification row instead, so it's visible without being able to
break the actual claims pipeline.
"""

from __future__ import annotations

import asyncio
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, Customer, Notification
from app.config import settings
from app.connectors.communication import send_email, send_sms


class NotificationEvent(str, Enum):
    SUBMITTED = "claim_submitted"
    UNDER_REVIEW = "decision_referred"
    APPROVED = "decision_approved"
    DECLINED = "decision_declined"


_SUBJECT_BY_EVENT: dict[NotificationEvent, str] = {
    NotificationEvent.SUBMITTED: "We've received your claim",
    NotificationEvent.UNDER_REVIEW: "Your claim is being reviewed",
    NotificationEvent.APPROVED: "Update on your claim",
    NotificationEvent.DECLINED: "Update on your claim",
}

# coverage_decision / DECISION_REFER string values from decision_service.py
# -> which event this maps to. Kept here (not imported from
# decision_service) to avoid a circular import - decision_service calls
# into this module, not the other way around.
_EVENT_BY_DECISION: dict[str, NotificationEvent] = {
    "covered": NotificationEvent.APPROVED,
    "partial": NotificationEvent.APPROVED,
    "excluded": NotificationEvent.DECLINED,
    "refer_to_assessor": NotificationEvent.UNDER_REVIEW,
}


def event_for_decision(decision: str) -> NotificationEvent:
    return _EVENT_BY_DECISION.get(decision, NotificationEvent.UNDER_REVIEW)


async def notify_customer(
    db: AsyncSession,
    *,
    claim: Claim,
    event: NotificationEvent,
    message: str,
    decision_id: int | None = None,
) -> None:
    """Sends via whichever channels the claimant has contact info for
    (email if an address is on file, SMS if a phone number is), and always
    persists one Notification row per channel attempted - a failed send is
    still worth recording, not silently dropped.

    NOTIFICATIONS_ENABLED=false turns this off entirely: nothing attempted
    """
    if not settings.notifications_enabled:
        return

    customer =await db.get(Customer, claim.customer_id) if claim.customer_id else None
    email = claim.claimant_email or (customer.email if customer else None)
    phone = claim.claimant_phone or (customer.phone if customer else None)
    subject = _SUBJECT_BY_EVENT[event]

    if email:
        sent = await asyncio.to_thread(send_email, email, subject, message)
        db.add(Notification(
            claim_id=claim.claim_id, customer_id=claim.customer_id, decision_id=decision_id,
            type="email", message=message, trigger_source=event.value,
            status="sent" if sent else "failed",
        ))

    if phone:
        sent = await asyncio.to_thread(send_sms, phone, message)
        db.add(Notification(
            claim_id=claim.claim_id, customer_id=claim.customer_id, decision_id=decision_id,
            type="sms", message=message, trigger_source=event.value,
            status="sent" if sent else "failed",
        ))

    if email or phone:
        await db.commit()


async def notify_claim_submitted(db: AsyncSession, claim: Claim) -> None:
    message = (
        f"Hi {claim.claimant_name or 'there'}, we've received your claim "
        f"({claim.claim_reference}) and it's now being reviewed. We'll be in "
        f"touch as soon as there's an update. Thank you for your patience."
    )
    await notify_customer(db, claim=claim, event=NotificationEvent.SUBMITTED, message=message)
