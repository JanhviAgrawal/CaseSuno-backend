"""
Solution for: common/tests.py
Build Plan Reference: Section 12, Step 1 (Pages 18-19)

Tests the state machine transitions:
1. Requirement transitions (confirming 409 on skip, reverse, or terminal state changes).
2. Payment transitions (confirming 409 on invalid changes).
3. Matter transitions (confirming 409 on invalid changes).
"""

from django.test import SimpleTestCase
from common.services.state_machine import (
    REQUIREMENT_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    MATTER_TRANSITIONS,
    assert_transition,
    InvalidTransitionError,
)


class StateMachineUnitTests(SimpleTestCase):
    """
    Build Plan Section 12, Step 1:
    Parametrized tests confirming every illegal transition raises 409
    for Requirement, Payment and Matter, before anything else.
    """

    def test_illegal_requirement_transitions_raise_409(self):
        illegal_cases = [
            ("new", "reviewed"),        # skipped intermediate states
            ("reviewed", "contacted"),  # reversed state
            ("converted", "new"),       # modified terminal state
            ("new", "converted"),       # invalid jump to terminal
        ]
        for current, target in illegal_cases:
            with self.subTest(current=current, target=target):
                with self.assertRaises(InvalidTransitionError) as ctx:
                    assert_transition(REQUIREMENT_TRANSITIONS, current, target)
                self.assertEqual(ctx.exception.status_code, 409)

    def test_valid_requirement_transitions(self):
        valid_cases = [
            ("new", "contacted"),
            ("contacted", "information_received"),
            ("information_received", "reviewed"),
            ("reviewed", "service_proposed"),
            ("service_proposed", "payment_pending"),
            ("payment_pending", "converted"),
        ]
        for current, target in valid_cases:
            with self.subTest(current=current, target=target):
                assert_transition(REQUIREMENT_TRANSITIONS, current, target)

    def test_illegal_payment_transitions_raise_409(self):
        illegal_cases = [
            ("pending", "refunded"),  # cannot refund without being paid
            ("failed", "paid"),       # terminal state cannot be paid
            ("refunded", "paid"),     # terminal state cannot be paid
        ]
        for current, target in illegal_cases:
            with self.subTest(current=current, target=target):
                with self.assertRaises(InvalidTransitionError) as ctx:
                    assert_transition(PAYMENT_TRANSITIONS, current, target)
                self.assertEqual(ctx.exception.status_code, 409)

    def test_valid_payment_transitions(self):
        valid_cases = [
            ("pending", "paid"),
            ("pending", "failed"),
            ("paid", "refunded"),
        ]
        for current, target in valid_cases:
            with self.subTest(current=current, target=target):
                assert_transition(PAYMENT_TRANSITIONS, current, target)

    def test_illegal_matter_transitions_raise_409(self):
        illegal_cases = [
            ("active", "completed"),    # cannot skip in_progress
            ("completed", "active"),    # cannot reverse to active
            ("closed", "in_progress"),  # closed is terminal
        ]
        for current, target in illegal_cases:
            with self.subTest(current=current, target=target):
                with self.assertRaises(InvalidTransitionError) as ctx:
                    assert_transition(MATTER_TRANSITIONS, current, target)
                self.assertEqual(ctx.exception.status_code, 409)

    def test_valid_matter_transitions(self):
        valid_cases = [
            ("active", "in_progress"),
            ("in_progress", "awaiting_customer"),
            ("awaiting_customer", "in_progress"),
            ("in_progress", "completed"),
            ("completed", "closed"),
        ]
        for current, target in valid_cases:
            with self.subTest(current=current, target=target):
                assert_transition(MATTER_TRANSITIONS, current, target)
