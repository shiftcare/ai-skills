import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

import { captureToolTrace } from '../runners/claude.mjs';

test('Claude tool calls and errors are normalized', async () => {
  const messages = JSON.parse(await readFile(new URL('fixtures/claude_messages.json', import.meta.url)));
  const state = { toolCalls: [], callsById: new Map() };

  for (const message of messages) captureToolTrace(message, state);

  assert.deepEqual(state.toolCalls, [{
    name: 'whoami',
    input: {},
    output: 'Invented tool failure',
    isError: true,
  }]);
});

test('Claude read-only evaluations allow supported reads and deny every other MCP call', () => {
  // Mock the external SDK query boundary in a fresh process; run the real runner.
  const child = spawnSync(process.execPath, ['--experimental-test-module-mocks', '--input-type=module', '-e', `
    import assert from 'node:assert/strict';
    import { mock } from 'node:test';
    mock.module('@anthropic-ai/claude-agent-sdk', { namedExports: {
      query: async function* ({options}) {
        assert.ok(!options.allowedTools?.includes('mcp__shiftcare'), 'server-wide permission allows writes');
        for (const [name, expected] of [
          ['mcp__shiftcare__whoami', 'allow'],
          ['mcp__shiftcare__list_teams', 'allow'],
          ['mcp__shiftcare__list_clients', 'allow'],
          ['mcp__shiftcare__list_shifts', 'allow'],
          ['mcp__shiftcare__list_invoices', 'allow'],
          ['mcp__shiftcare__write_tool', 'deny'],
          ['mcp__shiftcare__create_shift', 'deny'],
          ['mcp__shiftcare__list_invented_unsupported_records', 'deny'],
          ['mcp__other__list_clients', 'deny'],
        ]) {
          const hook = options.hooks?.PreToolUse?.find(({matcher}) => new RegExp(matcher).test(name));
          assert.ok(hook, 'MCP calls must pass an explicit permission gate');
          const result = await hook.hooks[0]({tool_name: name, tool_input: {}}, undefined, {});
          assert.equal(result.hookSpecificOutput.permissionDecision, expected, name);
        }
        yield { type: 'result', subtype: 'success', result: 'Invented answer',
          usage: { input_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, output_tokens: 1 },
          total_cost_usd: 0.01, duration_ms: 1, num_turns: 1 };
      },
    }});
    const { runClaude } = await import('./runners/claude.mjs');
    const result = await runClaude({ prompt: 'Invented prompt', model: 'invented-model', cwd: '/invented',
      skill: null, mcp: { url: 'https://mcp.au.shiftcare.com/mcp', token: 'invented-test-only' } });
    assert.equal(result.answer, 'Invented answer');
  `], { cwd: new URL('..', import.meta.url), encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr);
});
