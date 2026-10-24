from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare daily rundown"
SKILL = "shiftcare-daily-rundown"
# Asks are phrased the way a coordinator would say them. Spelling out the sweep
# in the prompt would hand the no-skill arm the skill's procedure and measure
# nothing.
CASES = [
    {
        "name": "morning rundown reports today's problems with next steps",
        "ask": "What needs my attention today? Give me the morning rundown.",
        "expected_tools": ["list_shifts", "list_shift_staffs"],
        "quality": (
            "Reports what needs a coordinator's attention today from actual shift data, "
            "grouped by urgency, each finding naming the shift, client, staff member or "
            "vacancy and a concrete next step, or clearly states nothing needs attention; "
            "says which checks it could not run. Does not fabricate findings or claim to "
            "have changed anything."
        ),
        "activates": True,
        "shift_date": "today",
    },
    # A client cancellation with charge leaves cancelled_at empty and sets
    # absent_reason on each client instead, so these two cases check that such
    # shifts drop out of the sweep. The live account may have none on the day,
    # so each rubric accepts a plain "none today" and penalises an invented one.
    {
        "name": "shifts every client cancelled are left out of the rundown",
        "ask": "A couple of clients rang in to cancel today. What still needs my attention?",
        "expected_tools": ["list_shifts", "list_shift_staffs"],
        "quality": (
            "Treats a shift as cancelled when cancelled_at is set or when every client on "
            "it has an absent_reason (a client cancellation with charge, which leaves "
            "cancelled_at empty), and does not report any such shift as vacant, as a "
            "missed clock-in, or as a break problem. Reports the remaining findings with "
            "a concrete next step, or clearly states nothing needs attention, and says "
            "which checks it could not run. If no shift today was cancelled, says so "
            "rather than inventing one. Does not claim to have changed anything."
        ),
        "activates": True,
        "shift_date": "today",
    },
    {
        "name": "group shifts with some clients cancelled stay in the rundown",
        "ask": (
            "One of the clients on today's group shift cancelled but the others are "
            "still going. Is there anything I need to sort out today?"
        ),
        "expected_tools": ["list_shifts", "list_shift_staffs"],
        "quality": (
            "Keeps a group shift on which only some clients have an absent_reason in the "
            "rundown: it is still checked for cover and clock-ins for the clients who are "
            "still attending, and only the absent clients are left out of those checks. "
            "Does not treat that shift as cancelled, since that needs cancelled_at set or "
            "every client absent. If no group shift today has a partly cancelled client "
            "list, says so rather than inventing one. Does not claim to have changed "
            "anything."
        ),
        "activates": True,
        "shift_date": "today",
    },
    {
        "name": "account setup is deferred to the onboarding check",
        "ask": "Is my account set up properly? Give me an onboarding checklist.",
        "expected_tools": [],
        "quality": (
            "Treats this as account setup rather than a daily rundown: either gives a "
            "setup checklist from actual account data or points to the onboarding check, "
            "without producing a shift rundown. Does not fabricate setup findings or "
            "claim to have changed anything."
        ),
        "activates": False,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
