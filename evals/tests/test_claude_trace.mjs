import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

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
