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
ALLOWED_TOOLS = set(json.loads(Path(__file__).with_name("read_tools.json").read_text()))
# Calls the skill instructs before any ShiftCare data call, so they must not count
# as "the first call" when checking the connection protocol.
PRELUDE_TOOLS = {"check_skill_compatibility"}


def is_read_call(name):
    """Whether a tool call satisfies the connection protocol's "then read" step.

    Deliberately the harness allowlist rather than a name prefix: an agent can
    only call what the runner permits, so anything outside this set is either a
    write or a tool that does not exist, and neither should count as a read.
    """
    return name != "whoami" and name in ALLOWED_TOOLS
TRUNCATION_MARKERS = (
    "exceeds maximum allowed tokens",
    "Output has been saved to",
)


def loaded_skill(call, skill):
    if call["name"] == "Skill":
        return skill in json.dumps(call.get("input") or {})
    if call["name"] == "command_execution":
        return f"{skill}/SKILL.md" in json.dumps(call.get("input") or {})
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
    def __init__(self, tool_calls, expected, skill):
        self.tool_calls = tool_calls
        self.expected = expected
        self.skill = skill
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        observed = any(loaded_skill(call, self.skill) for call in self.tool_calls)
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
    """Deterministic check of the skill's Verify steps: whoami first, then at least one read.

    Only meaningful on the with-skill arm; the no-skill agent is never told this
    protocol. `test_connection.py` is what enforces that.
    """

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.threshold = 1
        self.async_mode = False
        self.include_reason = True
        self.evaluation_model = "deterministic"

    def measure(self, test_case, *args, **kwargs):
        calls = [call["name"] for call in self.tool_calls if call["name"] not in SKILL_LOADING_TOOLS]
        # The skill documents check_skill_compatibility as the first call of a task,
        # so whoami has to be the first call for ShiftCare *data*, not the first MCP
        # call outright. 14 of 20 with-skill results failed on this alone.
        calls = [name for name in calls if name not in PRELUDE_TOOLS]
        problems = []
        if not calls or calls[0] != "whoami":
            problems.append(f"first ShiftCare call was {calls[0] if calls else 'nothing'}, expected whoami")
        # Scoring against read_tools.json alone failed an agent that legitimately
        # read list_accounts, but "any call at all" would let a write satisfy the
        # step, so accept the allowlist plus anything named as a read.
        if not any(is_read_call(name) for name in calls[1:]):
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
