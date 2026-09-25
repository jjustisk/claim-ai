"""State machine tests."""

from __future__ import annotations

import pytest

from app.models.states import ClaimState, InvalidStateTransition, transition


def test_valid_happy_path():
    state = ClaimState.RECEIVED
    state = transition(state, ClaimState.PROCESSING)
    state = transition(state, ClaimState.SANITIZED)
    state = transition(state, ClaimState.VALIDATED)
    state = transition(state, ClaimState.READY_FOR_LLM)
    assert state == ClaimState.READY_FOR_LLM


def test_invalid_skip_sanitize():
    with pytest.raises(InvalidStateTransition):
        transition(ClaimState.RECEIVED, ClaimState.READY_FOR_LLM)
