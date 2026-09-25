"""Claim processing state machine."""

from __future__ import annotations

from enum import Enum


class ClaimState(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    SANITIZED = "SANITIZED"
    VALIDATED = "VALIDATED"
    READY_FOR_LLM = "READY_FOR_LLM"
    REHYDRATION_REQUESTED = "REHYDRATION_REQUESTED"
    REHYDRATED = "REHYDRATED"
    SANITIZATION_ERROR = "SANITIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REHYDRATION_ERROR = "REHYDRATION_ERROR"
    ACCESS_DENIED = "ACCESS_DENIED"


ALLOWED_TRANSITIONS: dict[ClaimState, set[ClaimState]] = {
    ClaimState.RECEIVED: {ClaimState.PROCESSING, ClaimState.SANITIZATION_ERROR},
    ClaimState.PROCESSING: {
        ClaimState.SANITIZED,
        ClaimState.SANITIZATION_ERROR,
        ClaimState.PROCESSING,
    },
    ClaimState.SANITIZED: {
        ClaimState.VALIDATED,
        ClaimState.VALIDATION_ERROR,
        ClaimState.PROCESSING,  # re-sanitize
    },
    ClaimState.VALIDATED: {
        ClaimState.READY_FOR_LLM,
        ClaimState.VALIDATION_ERROR,
        ClaimState.PROCESSING,  # re-sanitize
    },
    ClaimState.READY_FOR_LLM: {
        ClaimState.REHYDRATION_REQUESTED,
        ClaimState.READY_FOR_LLM,
        ClaimState.PROCESSING,  # re-sanitize after redaction fixes
    },
    ClaimState.REHYDRATION_REQUESTED: {
        ClaimState.REHYDRATED,
        ClaimState.REHYDRATION_ERROR,
        ClaimState.ACCESS_DENIED,
    },
    ClaimState.REHYDRATED: {
        ClaimState.REHYDRATION_REQUESTED,
        ClaimState.REHYDRATED,
        ClaimState.READY_FOR_LLM,
    },
    ClaimState.SANITIZATION_ERROR: {ClaimState.PROCESSING, ClaimState.RECEIVED},
    ClaimState.VALIDATION_ERROR: {ClaimState.SANITIZED, ClaimState.PROCESSING},
    ClaimState.REHYDRATION_ERROR: {
        ClaimState.REHYDRATION_REQUESTED,
        ClaimState.READY_FOR_LLM,
    },
    ClaimState.ACCESS_DENIED: {
        ClaimState.READY_FOR_LLM,
        ClaimState.REHYDRATION_REQUESTED,
    },
}


class InvalidStateTransition(Exception):
    def __init__(self, current: ClaimState, target: ClaimState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition: {current.value} → {target.value}")


def can_transition(current: ClaimState, target: ClaimState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(current: ClaimState, target: ClaimState) -> ClaimState:
    if not can_transition(current, target):
        raise InvalidStateTransition(current, target)
    return target
