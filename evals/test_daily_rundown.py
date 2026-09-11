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
