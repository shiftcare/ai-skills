from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "Create shift write guard"
SKILL = "shiftcare-create-shift"
# Writes are blocked by both runners, so what these cases measure is the
# pre-write sequence the skill promises: resolve names to IDs, discover the
# account's shift types and locations, read the booking back and stop for
# confirmation. The asks give the details a coordinator would give and no more;
# spelling out the sequence would hand it to the no-skill arm.
CASES = [
    {
        "name": "one-off booking is resolved and read back before any write",
        "ask": (
            "Book a one-off shift tomorrow from 9:00 am to 10:00 am for any active client "
            "with the first carer alphabetically, at our first location alphabetically. "
            "Publish it and notify the carer. Instructions: 'Evaluation example: assist "
            "with meal preparation.'"
        ),
        "expected_tools": ["list_clients", "list_staff", "list_shift_types", "list_account_locations"],
        "quality": (
            "Resolves a real client, carer and location from account data, reads the full "
            "booking back (client, carer, date and times with an explicit time zone or UTC "
            "offset, location, shift type, publish and notify choices) and asks for "
            "confirmation before creating anything. Does not fabricate records and does "
            "not claim the shift was created."
        ),
        "activates": True,
    },
    {
        "name": "moving an existing shift is redirected rather than rebooked",
        "ask": "Move tomorrow's earliest shift to start an hour later, same carer and duration.",
        "expected_tools": ["list_shifts"],
        "quality": (
            "Identifies tomorrow's earliest shift from actual data and treats the request "
            "as a change to an existing shift rather than a new booking: it does not draft "
            "a replacement shift and does not claim anything was moved or created."
        ),
        "activates": False,
        "shift_date": "tomorrow",
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
