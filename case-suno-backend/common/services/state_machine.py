"""
Solution for: common/services/state_machine.py
Build Plan Reference: Section 5 (Pages 7-8)

Changes Made:
1. Added PAYMENT_TRANSITIONS (pending -> paid, failed; paid -> refunded).
2. Added is_valid_payment_transition helper.
3. Added assert_transition() function raising HTTP 409 InvalidTransitionError.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class InvalidTransitionError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Invalid state transition."
    default_code = "invalid_transition"

    def __init__(self, current: str, target: str):
        detail = {
            "error": "invalid_transition",
            "from": current,
            "to": target,
        }
        super().__init__(detail=detail)


REQUIREMENT_TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacted"},
    "contacted": {"information_received"},
    "information_received": {"reviewed"},
    "reviewed": {"service_proposed"},
    "service_proposed": {"payment_pending"},
    "payment_pending": {"converted"},
    "converted": set(),
}


def is_valid_requirement_transition(current: str, target: str) -> bool:
    return target in REQUIREMENT_TRANSITIONS.get(current, set())


PAYMENT_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"paid", "failed"},
    "paid": {"refunded"},
    "failed": set(),
    "refunded": set(),
}


def is_valid_payment_transition(current: str, target: str) -> bool:
    return target in PAYMENT_TRANSITIONS.get(current, set())


MATTER_TRANSITIONS: dict[str, set[str]] = {
    "active": {"in_progress"},
    "in_progress": {"awaiting_customer", "completed"},
    "awaiting_customer": {"in_progress"},
    "completed": {"closed"},
    "closed": set(),
}


def is_valid_matter_transition(current: str, target: str) -> bool:
    return target in MATTER_TRANSITIONS.get(current, set())


def assert_transition(transitions: dict[str, set[str]], current: str, target: str) -> None:
    """
    Enforce state transition rules. Raises HTTP 409 Conflict if illegal.
    Matches PDF specification Page 8: assert_transition(...)
    """
    if target not in transitions.get(current, set()):
        raise InvalidTransitionError(current=current, target=target)
