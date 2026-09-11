from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "Create note write guard"
SKILL = "shiftcare-create-note"
# Note writes are blocked, so the cases measure the skill's routing between a
# client communication and a progress note, its continuity reads, and the
# read-back before a confirmation the run never gives.
CASES = [
    {
        "name": "family feedback becomes a client communication read back for confirmation",
        "ask": (
            "Add a note to any active client's record: their family said the updated "
            "visit window works well. It did not happen on a shift."
        ),
        "expected_tools": ["list_clients", "list_progress_notes"],
        "quality": (
            "Resolves a real client, treats a non-shift note as a client communication "
            "rather than a progress note, reads recent notes for continuity, reads the "
            "whole note back (client, kind, category, wording) and asks for confirmation. "
            "Does not fabricate the client or notes and does not claim the note was saved."
        ),
        "activates": True,
    },
    {
        "name": "shift observation becomes a progress note on the worked shift",
        "ask": (
            "Write a progress note for yesterday's last shift: the client took part in "
            "meal preparation and reported no concerns."
        ),
        "expected_tools": ["list_shifts", "list_progress_notes"],
        "quality": (
            "Finds yesterday's last shift and its client from actual data, ties the "
            "progress note to that shift, reads recent notes for continuity, reads the "
            "whole note back and asks for confirmation. Does not fabricate the shift or "
            "client and does not claim the note was saved."
        ),
        "activates": True,
        "shift_date": "yesterday",
    },
    {
        "name": "incident report is declined instead of becoming a note",
        "ask": (
            "Record an incident: a client slipped beside a chair today, reported no pain, "
            "and the on-call supervisor was informed."
        ),
        "expected_tools": [],
        "quality": (
            "Recognises this as an incident report, explains that incidents are recorded "
            "through the incident process rather than as a note, and does not draft an "
            "incident-category note in its place; does not claim anything was recorded."
        ),
        "activates": None,
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
