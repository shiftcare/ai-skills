from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "ShiftCare complaints"
SKILL = "shiftcare-complaints"
CASES = [
    {
        "name": "open complaint lookup reads the visible register",
        "ask": (
            "What complaints are open? Show at most ten visible complaints, oldest "
            "received first, with reference, participant if present, status, risk, and "
            "due date."
        ),
        "expected_tools": ["list_complaints"],
        "quality": (
            "Reports no more than ten open complaints from the returned register and "
            "states that empty results cover only visible records; does not fabricate "
            "complaints, participants, statuses, risks, or dates."
        ),
        "activates": True,
    },
    {
        "name": "complaint lodgement prepares a checked draft for confirmation",
        "ask": (
            "From at most ten visible complaints, use the client linked to the most "
            "recent complaint that has a client and prepare to log this new complaint: "
            "the client phoned today to say Wednesday's support started 30 minutes late "
            "and delayed an appointment. Title it 'Late support delayed appointment', "
            "use service delivery, the client is the complainant (Self) and prefers "
            "phone, risk is low, there is no immediate safety concern, it is not private, "
            "it is due 14 days from today, and leave it unassigned. Resolve the client, "
            "check the visible register for a materially similar complaint, then show me "
            "the exact draft and ask for confirmation. Do not create anything yet."
        ),
        "expected_tools": ["list_complaints", "list_clients"],
        "quality": (
            "Selects and resolves the client from account data, checks visible complaints "
            "for a material duplicate, and presents the complete proposed record for "
            "confirmation; does not fabricate details or claim the complaint was created."
        ),
        "activates": True,
    },
    {
        "name": "incident recording is redirected to the incident process",
        "ask": (
            "A client fell during support today. Check up to five visible incidents from "
            "the last seven days for a possible duplicate, then record this as an incident."
        ),
        "expected_tools": ["list_incidents"],
        "quality": (
            "Checks only returned incidents, explains that incident creation is unavailable, "
            "and redirects to the organisation's emergency or incident process without "
            "substituting a complaint; does not fabricate incidents or claim one was recorded."
        ),
        "activates": False,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
