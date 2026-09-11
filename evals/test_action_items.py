from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare action items"
SKILL = "shiftcare-action-items"
CASES = [
    {
        "name": "overdue action item lookup uses the overdue filter",
        "ask": (
            "Which corrective action items are overdue? Show at most ten visible items, "
            "oldest due first, with title, parent if any, assignee, status, priority, and "
            "due date."
        ),
        "expected_tools": ["list_action_items"],
        "quality": (
            "Uses the overdue filter and reports no more than ten returned live overdue "
            "items, noting that empty results cover only visible records; does not "
            "fabricate action items or their details."
        ),
        "activates": True,
    },
    {
        "name": "corrective action suggestions inspect the complaint and existing work",
        "ask": (
            "From at most ten visible complaints, select the most recently created one, "
            "inspect it and up to ten action items already awaiting work on it, then "
            "propose a short corrective-action shortlist for my approval. Do not create "
            "anything yet."
        ),
        "expected_tools": [
            "list_complaints",
            "get_complaint",
            "list_action_items",
        ],
        "quality": (
            "Bases specific, assignable suggestions only on the selected complaint and "
            "its live existing actions, respects the complaint's one-to-three-item risk "
            "cap, and asks for approval; does not fabricate details or claim any action "
            "item was created."
        ),
        "activates": True,
    },
    {
        "name": "action item sign off is identified as app only",
        "ask": (
            "Find the most recent action item awaiting verification and sign it off. "
            "Limit the lookup to one item."
        ),
        "expected_tools": ["list_action_items"],
        "quality": (
            "Identifies at most one returned item awaiting verification, explains that "
            "sign-off is app-only, and stops; does not fabricate an item or claim its "
            "status changed."
        ),
        "activates": None,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
