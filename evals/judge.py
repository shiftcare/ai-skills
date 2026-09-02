import asyncio

from deepeval.models import DeepEvalBaseLLM

from runners import run_agent


class ClaudeJudge(DeepEvalBaseLLM):
    def __init__(self, workspaces):
        self.cwd = workspaces["no-skill"]
        super().__init__("sonnet")

    def load_model(self):
        return self.name

    def generate(self, prompt):
        return run_agent(
            prompt,
            "sonnet",
            cwd=self.cwd,
            skill=None,
            mcp=None,
        )["answer"]

    async def a_generate(self, prompt):
        return await asyncio.to_thread(self.generate, prompt)

    def get_model_name(self):
        return "Claude Agent SDK (sonnet)"
