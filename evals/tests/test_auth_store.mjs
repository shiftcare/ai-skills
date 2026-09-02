import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { FileOAuthProvider, validAccessToken } from '../auth.mjs';

test('saved tokens round-trip through the auth store', async (t) => {
  const authDir = await mkdtemp(path.join(os.tmpdir(), 'mcp-eval-auth-'));
  t.after(() => rm(authDir, { recursive: true, force: true }));
  const provider = new FileOAuthProvider(
    new URL('https://mcp.example.invalid/mcp'),
    'http://127.0.0.1:12345/callback',
    authDir,
  );
  const before = Date.now();

  await provider.saveTokens({ access_token: 'invented-access-token', token_type: 'bearer', expires_in: 60 });
  const saved = await provider.tokens();

  assert.equal(saved.access_token, 'invented-access-token');
  assert.equal(saved.token_type, 'bearer');
  assert.equal(saved.expires_in, 60);
  assert.ok(saved.expires_at >= before + 60_000);
  assert.ok(saved.expires_at <= Date.now() + 60_000);
});

test('a saved unexpired access token is valid without a refresh token', async (t) => {
  const authDir = await mkdtemp(path.join(os.tmpdir(), 'mcp-eval-auth-'));
  t.after(() => rm(authDir, { recursive: true, force: true }));
  const provider = new FileOAuthProvider(
    new URL('https://mcp.example.invalid/mcp'),
    'http://127.0.0.1:12345/callback',
    authDir,
  );
  const now = Date.now();

  await provider.saveTokens({ access_token: 'invented-access-token', expires_at: now + 3_600_000 });
  const saved = await provider.tokens();

  assert.equal(saved.refresh_token, undefined);
  assert.equal(validAccessToken(saved, now), 'invented-access-token');
});
