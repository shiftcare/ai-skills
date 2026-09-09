import asyncio
import os

from deepeval.models import DeepEvalBaseLLM

from runners import run_agent


_JUDGE_SLOTS = asyncio.Semaphore(int(os.getenv("EVAL_JUDGE_CONCURRENCY", "4")))


class ClaudeJudge(DeepEvalBaseLLM):
    def __init__(self, workspaces):
        self.cwd = workspaces["no-skill"]
        super().__init__(os.getenv("EVAL_JUDGE_MODEL", "sonnet"))

    def load_model(self):
        return self.name

    def generate(self, prompt):
        return run_agent(
            prompt,
            self.name,
            cwd=self.cwd,
            skill=None,
            mcp=None,
        )["answer"]

    async def a_generate(self, prompt):
        async with _JUDGE_SLOTS:
            return await asyncio.to_thread(self.generate, prompt)

    def get_model_name(self):
        runner = "Codex CLI" if self.name.startswith("gpt-") else "Claude Agent SDK"
        return f"{runner} ({self.name})"
