import json
from pathlib import Path

from deepeval.metrics import (
    ArgumentCorrectnessMetric as DeepEvalArgumentCorrectnessMetric,
    BaseMetric,
    StepEfficiencyMetric,
    TaskCompletionMetric,
)
from deepeval.test_case import ToolCall


SKILL_LOADING_TOOLS = {"Skill", "command_execution"}
READ_TOOLS = set(json.loads(Path(__file__).with_name("read_tools.json").read_text())) - {"whoami"}
TRUNCATION_MARKERS = (
    "exceeds maximum allowed tokens",
    "Output has been saved to",
)


def loaded_shiftcare_mcp(call):
    if call["name"] == "Skill":
        return "shiftcare-mcp" in json.dumps(call.get("input") or {})
    if call["name"] == "command_execution":
        return "shiftcare-mcp/SKILL.md" in json.dumps(call.get("input") or {})
    return False



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


def _argument_correctness_case(test_case):
    return test_case.model_copy(
        update={
            "tools_called": [
                call
                for call in test_case.tools_called
                if call.name not in SKILL_LOADING_TOOLS and call.input_parameters
            ]
        }
    )


class ArgumentCorrectnessMetric(DeepEvalArgumentCorrectnessMetric):
    def measure(self, test_case, *args, **kwargs):
        return super().measure(_argument_correctness_case(test_case), *args, **kwargs)


def agentic_metrics(judge, task):
    return [
        TaskCompletionMetric(task=task, model=judge, async_mode=True),
        StepEfficiencyMetric(model=judge, async_mode=True),
        ArgumentCorrectnessMetric(model=judge, async_mode=True),
    ]


def agent_trace(test_case, tool_calls):
    return {
        "name": "agent",
        "type": "agent",
        "input": test_case.input,
        "output": test_case.actual_output,
        "children": [
            {
                "name": call["name"],
                "type": "tool",
                "input": {"inputParameters": call.get("input") or {}},
                "output": call.get("output"),
                "error": "Tool call failed" if call.get("isError") else None,
                "children": [],
            }
            for call in tool_calls
        ],
    }


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


class SkillActivation(BaseMetric):
    def __init__(self, tool_calls, expected):
        self.tool_calls = tool_calls
        self.expected = expected
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        observed = any(loaded_shiftcare_mcp(call) for call in self.tool_calls)
        self.score = int(observed == self.expected)
        self.reason = f"Skill activation was {observed}; expected {self.expected}."
        self.success = self.is_successful()
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self):
        self.success = self.error is None and self.score is not None and self.score >= self.threshold
        return self.success

    @property
    def __name__(self):
        return "Skill Activation"


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
        if not any(name in READ_TOOLS for name in calls[1:]):
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


class ShiftDate(BaseMetric):
    def __init__(self, tool_calls, expected_date):
        self.tool_calls = tool_calls
        self.expected_date = expected_date
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        call = next((call for call in self.tool_calls if call["name"] == "list_shifts"), None)
        self.score = int(call is not None and self.expected_date in json.dumps(call.get("input") or {}))
        self.reason = (
            f"list_shifts used the expected date {self.expected_date}."
            if self.score else f"Expected list_shifts with date {self.expected_date}; "
            + ("tool was not called." if call is None else "arguments did not include that date.")
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
        return "Shift Date"
