from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "Read-only tasks"
SKILL = "shiftcare-mcp"
CASES = [
    {
        "name": "client lookup returns up to five active clients",
        "ask": "Name up to five active clients.",
        "expected_tools": ["list_clients"],
        "quality": (
            "Names no more than five real active clients from the account; does not "
            "fabricate clients or claim it has no access."
        ),
        "activates": False,
    },
    {
        "name": "schedule question picks list_shifts with tomorrow's date",
        "ask": "What shifts are scheduled for tomorrow?",
        "expected_tools": ["list_shifts"],
        "quality": (
            "Reports tomorrow's shifts (or clearly states there are none); does not "
            "invent shifts."
        ),
        "activates": False,
        "shift_date": "tomorrow",
    },
    {
        "name": "team lookup returns up to five teams",
        "ask": "Name up to five ShiftCare teams.",
        "expected_tools": ["list_teams"],
        "quality": "Names no more than five real teams and does not fabricate teams.",
        "activates": False,
    },
    {
        "name": "invoice question picks list_invoices",
        "ask": "Do we have any unpaid invoices?",
        "expected_tools": ["list_invoices"],
        "quality": (
            "Answers based on actual invoice data (or clearly states none found); does "
            "not fabricate amounts."
        ),
        "activates": False,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
