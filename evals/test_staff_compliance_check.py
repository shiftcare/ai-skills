from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare staff compliance check"
SKILL = "shiftcare-staff-compliance-check"
CASES = [
    {
        "name": "three-staff sweep reports credential status per person",
        "ask": (
            "Which of our staff have expired or expiring certifications? Check the first "
            "three staff alphabetically."
        ),
        "expected_tools": ["list_staff", "list_staff_qualifications"],
        "quality": (
            "Reports, for exactly three real staff members, which credentials are expired, "
            "expiring, missing or unverified, or states that none are, based on their "
            "actual qualification records, with a next step for each gap; does not "
            "declare the account compliant. Does not fabricate staff or records."
        ),
        "activates": True,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
