from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare basics routing"
SKILL = "shiftcare-basics"
CASES = [
    {
        "name": "shift notes route to progress notes for one client",
        "ask": (
            "Pick any one active client, then show up to five of their shift notes "
            "from the last 30 days."
        ),
        "expected_tools": ["list_clients", "list_progress_notes"],
        "quality": (
            "Uses one real active client and reports no more than five notes returned "
            "for that client in the requested window; does not fabricate clients, "
            "notes, authors, or dates."
        ),
        "activates": True,
    },
    {
        "name": "roster question resolves staff assignments for tomorrow",
        "ask": (
            "For tomorrow, choose one client who has at least one scheduled shift and "
            "tell me who is rostered on for up to five of that client's shifts."
        ),
        "expected_tools": ["list_shifts", "list_shift_staffs"],
        "quality": (
            "Uses tomorrow in the account time zone and reports no more than five real "
            "shifts for one client, naming only staff returned for each shift; does not "
            "fabricate shifts, clients, or staff."
        ),
        "activates": True,
        "shift_date": "tomorrow",
    },
    {
        "name": "connection troubleshooting stays outside the basics skill",
        "ask": "My ShiftCare tools are returning errors. Help me fix the connection.",
        "expected_tools": [],
        "quality": (
            "Treats this as connection setup rather than a domain question: points to "
            "connection troubleshooting or checks access with whoami, without walking "
            "through rostering or client workflows. Does not fabricate access details "
            "or claim the connection was fixed."
        ),
        "activates": False,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
