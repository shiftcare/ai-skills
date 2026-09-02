import json

from deepeval.metrics import BaseMetric
from deepeval.test_case import ToolCall


SKILL_LOADING_TOOLS = {"Skill", "command_execution"}
TRUNCATION_MARKERS = (
    "exceeds maximum allowed tokens",
    "Output has been saved to",
)



def to_deepeval_tool_calls(tool_calls):
    calls = []
    for call in tool_calls:
        output = call.get("output")
        if not isinstance(output, str):
            output = json.dumps(output)
        calls.append(
            ToolCall(
                name=call["name"],
                input_parameters=call.get("input") or {},
                output=output,
            )
        )
    return calls


class ToolResultIntegrity(BaseMetric):
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        problems = []
        for call in self.tool_calls:
            issues = []
            output = call.get("output")
            if call.get("isError"):
                issues.append("error")
            if output is None:
                issues.append("missing output")
            elif any(marker in (output if isinstance(output, str) else json.dumps(output))
                     for marker in TRUNCATION_MARKERS):
                issues.append("truncated output")
            if issues:
                problems.append(f"{call['name']} ({', '.join(issues)})")

        self.score = 0 if problems else 1
        self.reason = (
            f"Offending tool calls: {', '.join(problems)}"
            if problems
            else "All tool calls returned complete results."
        )
        self.success = self.is_successful()
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self):
        self.success = self.error is None and self.score is not None and self.score >= self.threshold
        return self.success

    @property
    def __name__(self):
        return "Tool Result Integrity"


class ConnectionProtocol(BaseMetric):
    """Deterministic check of the skill's Verify steps: whoami first, then at least one read."""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        calls = [call["name"] for call in self.tool_calls if call["name"] not in SKILL_LOADING_TOOLS]
        problems = []
        if not calls or calls[0] != "whoami":
            problems.append(f"first MCP call was {calls[0] if calls else 'nothing'}, expected whoami")
        if len(calls) < 2:
            problems.append("no read-only call after whoami")
        self.score = 0 if problems else 1
        self.reason = "; ".join(problems) if problems else f"whoami first, then {', '.join(calls[1:])}"
        self.success = self.is_successful()
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self):
        self.success = self.error is None and self.score is not None and self.score >= self.threshold
        return self.success

    @property
    def __name__(self):
        return "Connection Protocol"
