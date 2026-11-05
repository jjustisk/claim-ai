"""Customer notifications - email/SMS via Azure Communication Services, at
the points in a claim's life where the customer actually needs to hear
something: submission, and the outcome an assessor records on review
(approved/declined/still under review).

Never raises into the caller. A failed or unconfigured send doesn't stop a
claim being submitted or a review being recorded - it's recorded as a
"failed" Notification row instead, so it's visible without being able to
break the actual claims pipeline.
"""

from __future__ import annotations

import asyncio
import html
import logging
from contextlib import suppress
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, Customer, Notification
from app.config import settings
from app.connectors.communication import send_email, send_sms, sms_configured

logger = logging.getLogger(__name__)


class NotificationEvent(str, Enum):
    SUBMITTED = "claim_submitted"
    # The checks have finished and a person now has the claim. Not the same as
    # UNDER_REVIEW below, which is an assessor escalating a claim after reviewing it.
    WITH_ASSESSOR = "claim_with_assessor"
    UNDER_REVIEW = "decision_referred"
    APPROVED = "decision_approved"
    DECLINED = "decision_declined"


_SUBJECT_BY_EVENT: dict[NotificationEvent, str] = {
    NotificationEvent.SUBMITTED: "We've received your claim",
    NotificationEvent.WITH_ASSESSOR: "Your claim is with an assessor",
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


# Assessor review outcomes (reviews.outcome / claim.status values). "closed"
# has no customer email.
_EVENT_BY_REVIEW_OUTCOME: dict[str, NotificationEvent] = {
    "approved": NotificationEvent.APPROVED,
    "rejected": NotificationEvent.DECLINED,
    "under_review": NotificationEvent.UNDER_REVIEW,
}

_REVIEW_OPENING: dict[NotificationEvent, str] = {
    NotificationEvent.APPROVED: "our assessor has approved your claim ({reference}).",
    NotificationEvent.DECLINED: "our assessor has reviewed your claim ({reference}) and is unable to approve it.",
    NotificationEvent.UNDER_REVIEW: "your claim ({reference}) is still being reviewed by our assessors.",
}

_REVIEW_DEFAULT: dict[NotificationEvent, str] = {
    NotificationEvent.APPROVED: "We'll be in touch shortly about the next steps for settling your claim.",
    NotificationEvent.DECLINED: (
        "If you have any questions about this decision or would like it reviewed, please contact us."
    ),
    NotificationEvent.UNDER_REVIEW: (
        "We'll be in touch as soon as a decision has been made. Thank you for your patience."
    ),
}

# Which AI decisions an unedited AI customer explanation is consistent with.
_AI_DECISIONS_BY_EVENT: dict[NotificationEvent, set[str]] = {
    NotificationEvent.APPROVED: {"covered", "partial"},
    NotificationEvent.DECLINED: {"excluded"},
    NotificationEvent.UNDER_REVIEW: {"refer_to_assessor"},
}


def event_for_review_outcome(outcome: str) -> NotificationEvent | None:
    """Return the notification event for an assessor's review outcome, or None for no email."""
    return _EVENT_BY_REVIEW_OUTCOME.get(outcome)


def review_outcome_message(
    claim: Claim,
    event: NotificationEvent,
    explanation: str | None,
    *,
    ai_decision: str | None,
    edited: bool,
) -> str:
    """Return the customer message for a review outcome, using the explanation only when it fits."""
    opening = f"Hi {claim.claimant_name or 'there'}, " + _REVIEW_OPENING[event].format(
        reference=claim.claim_reference
    )
    text = html.unescape(explanation or "").strip()
    if not text or not (edited or ai_decision in _AI_DECISIONS_BY_EVENT[event]):
        text = _REVIEW_DEFAULT[event]
    return f"{opening}\n\n{text}"


async def notify_review_outcome(
    db: AsyncSession,
    *,
    claim_id: int,
    outcome: str,
    explanation: str | None,
    ai_decision: str | None = None,
    decision_id: int | None = None,
    edited: bool = False,
) -> None:
    """Notify the customer of an assessor's review outcome; never raises."""
    event = event_for_review_outcome(outcome)
    if event is None or not settings.notifications_enabled:
        return
    try:
        claim = await db.get(Claim, claim_id)
        if claim is None:
            return
        message = review_outcome_message(claim, event, explanation, ai_decision=ai_decision, edited=edited)
        await notify_customer(db, claim=claim, event=event, message=message, decision_id=decision_id)
    except Exception:
        logger.exception("Review outcome notification failed claim_id=%s outcome=%s", claim_id, outcome)
        with suppress(Exception):
            await db.rollback()


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

    if phone and sms_configured():
        sent = await asyncio.to_thread(send_sms, phone, message)
        db.add(Notification(
            claim_id=claim.claim_id, customer_id=claim.customer_id, decision_id=decision_id,
            type="sms", message=message, trigger_source=event.value,
            status="sent" if sent else "failed",
        ))

    if email or (phone and sms_configured()):
        await db.commit()


async def notify_claim_submitted(db: AsyncSession, claim: Claim) -> None:
    message = (
        f"Hi {claim.claimant_name or 'there'}, we've received your claim "
        f"({claim.claim_reference}) and it's now being reviewed. We'll be in "
        f"touch as soon as there's an update. Thank you for your patience."
    )
    await notify_customer(db, claim=claim, event=NotificationEvent.SUBMITTED, message=message)


async def notify_assessor_review(db: AsyncSession, *, claim_id: int, decision_id: int | None = None) -> None:
    """Tell the customer their claim has moved on to an assessor.

    Sent once per claim, whatever the pipeline outcome (a recommendation was saved, or the
    automatic checks could not run). It never says what the checks concluded: the customer
    hears the outcome only after an assessor has reviewed it. Never raises.
    """
    if not settings.notifications_enabled:
        return
    try:
        already_sent = (await db.execute(
            select(Notification.notif_id)
            .where(Notification.claim_id == claim_id, Notification.trigger_source == NotificationEvent.WITH_ASSESSOR.value)
            .limit(1)
        )).first()
        if already_sent:
            return
        claim = await db.get(Claim, claim_id)
        if claim is None:
            return
        message = (
            f"Hi {claim.claimant_name or 'there'}, your claim ({claim.claim_reference}) has been checked and "
            f"passed to one of our licensed assessors, who will review it and make the final decision. "
            f"We'll email you again as soon as there's an outcome."
        )
        await notify_customer(db, claim=claim, event=NotificationEvent.WITH_ASSESSOR, message=message, decision_id=decision_id)
    except Exception:
        logger.exception("Assessor-review notification failed claim_id=%s", claim_id)
        with suppress(Exception):
            await db.rollback()
