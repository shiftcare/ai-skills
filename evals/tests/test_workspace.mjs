import assert from 'node:assert/strict';
import { lstat, mkdir, mkdtemp, readFile, readlink, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { AGENT_INSTRUCTIONS, ensureWorkspaces } from '../workspace.mjs';

test('one isolated workspace is created for every discovered skill', async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'mcp-eval-workspaces-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const skill of ['invented-alpha', 'invented-beta']) {
    await mkdir(path.join(root, 'skills', skill), { recursive: true });
  }

  const workspaces = await ensureWorkspaces(root);

  assert.deepEqual(Object.keys(workspaces.skills), ['invented-alpha', 'invented-beta']);
  assert.equal(workspaces['no-skill'], path.join(root, 'evals', '.workspace', 'no-skill'));
  assert.equal(workspaces.home, path.join(root, 'evals', '.workspace', 'home'));
  for (const [skill, workspace] of Object.entries(workspaces.skills)) {
    assert.equal(workspace, path.join(root, 'evals', '.workspace', `with-${skill}`));
    assert.equal(await readFile(path.join(workspace, 'AGENTS.md'), 'utf8'), `${AGENT_INSTRUCTIONS}\n`);
    for (const client of ['.claude', '.agents']) {
      const link = path.join(workspace, client, 'skills', skill);
      assert.equal((await lstat(link)).isSymbolicLink(), true);
      assert.equal(path.resolve(path.dirname(link), await readlink(link)), path.join(root, 'skills', skill));
    }
  }
  assert.equal(
    await readFile(path.join(workspaces['no-skill'], 'AGENTS.md'), 'utf8'),
    `${AGENT_INSTRUCTIONS}\n`,
  );
  assert.equal((await lstat(path.join(workspaces.home, '.codex', 'auth.json'))).isSymbolicLink(), true);
});
