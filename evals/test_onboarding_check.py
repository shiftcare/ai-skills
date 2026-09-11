from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare onboarding check"
SKILL = "shiftcare-onboarding-check"
CASES = [
    {
        "name": "setup scorecard distinguishes sample data from entered data",
        "ask": "I'm new to ShiftCare. Is my account set up properly, and what is left to do?",
        "expected_tools": ["list_clients", "list_staff", "list_pay_groups", "list_shift_types"],
        "quality": (
            "Reports a setup scorecard from actual account data covering at least clients, "
            "staff, pay and shift types, with a concrete next step for each gap, and "
            "distinguishes the sample data new accounts start with from data a person "
            "entered. Does not fabricate setup evidence or claim to have changed anything."
        ),
        "activates": True,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
