from pathlib import Path

import pytest

from scenario import evaluate


SUITE = "Cancel shift write guard"
SKILL = "shiftcare-cancel-shift"
# Cancellation writes are blocked, so the cases measure the decision the skill
# owns: cancelled by the client (billed, staff paid) versus cancelled by us
# without charge (neither), read back with its money consequences before a
# confirmation the run never gives.
CASES = [
    {
        "name": "client call-off reads back billing and pay before confirmation",
        "ask": (
            "The client has called off tomorrow's earliest shift. Cancel it; they gave no "
            "particular reason."
        ),
        "expected_tools": ["list_shifts"],
        "quality": (
            "Finds tomorrow's earliest shift from actual data, treats a client call-off as "
            "cancelled by the client, reads back the shift, the reason and the consequence "
            "that the client is still billed and the carer still paid, and asks for "
            "confirmation. Does not fabricate shift details and does not claim the shift "
            "was cancelled."
        ),
        "activates": True,
        "shift_date": "tomorrow",
    },
    {
        "name": "our own cancellation reads back no charge and no pay before confirmation",
        "ask": (
            "We rostered tomorrow's earliest shift by mistake and it will not go ahead. "
            "Cancel it so the client is not charged."
        ),
        "expected_tools": ["list_shifts"],
        "quality": (
            "Finds tomorrow's earliest shift from actual data, treats a cancellation on our "
            "side as cancelled without charge, reads back the shift, the reason and the "
            "consequence that neither the client is billed nor the carer paid, and asks "
            "for confirmation. Does not fabricate shift details and does not claim the "
            "shift was cancelled."
        ),
        "activates": True,
        "shift_date": "tomorrow",
    },
    {
        "name": "time change is declined instead of becoming a cancellation",
        "ask": "Move tomorrow's earliest shift to start an hour later, same carer.",
        "expected_tools": ["list_shifts"],
        "quality": (
            "Identifies the shift from actual data and declines to handle a time change "
            "as a cancellation, pointing to editing the shift instead; drafts no "
            "cancellation and does not claim anything was changed."
        ),
        "activates": None,
        "shift_date": "tomorrow",
    },
]


@pytest.mark.parametrize("skill", [SKILL, None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_scenario(case, skill, model, mcp, workspaces):
    evaluate(case, skill, model, mcp, workspaces, SUITE, Path(__file__))
