import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { auth } from '@modelcontextprotocol/sdk/client/auth.js';

// Refresh tokens rotate on every use, so a request that hangs loses the login. Fail fast instead.
const fetchFn = (url, init) => fetch(url, { ...init, signal: AbortSignal.timeout(30_000) });

const evalsDir = path.dirname(fileURLToPath(import.meta.url));

export function validAccessToken(tokens, now = Date.now()) {
  return tokens?.access_token && Number.isFinite(tokens.expires_at) && tokens.expires_at > now + 30_000
    ? tokens.access_token
    : undefined;
}

export class FileOAuthProvider {
  constructor(serverUrl, redirectUrl, authDir = path.join(evalsDir, '.auth')) {
    this.redirectUrl = redirectUrl;
    this.clientMetadata = {
      client_name: 'mcp-eval-harness',
      redirect_uris: [redirectUrl],
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
      token_endpoint_auth_method: 'none',
    };
    this.authDir = authDir;
    this.file = path.join(authDir, `${serverUrl.hostname}.json`);
  }

  async read() {
    try {
      return JSON.parse(await readFile(this.file, 'utf8'));
    } catch (error) {
      if (error?.code === 'ENOENT') return {};
      throw error;
    }
  }

  async write(key, value) {
    const data = { ...(await this.read()), [key]: value };
    await mkdir(this.authDir, { recursive: true, mode: 0o700 });
    const temporary = `${this.file}.${process.pid}.tmp`;
    await writeFile(temporary, `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 });
    await rename(temporary, this.file);
  }

  async clientInformation() {
    return (await this.read()).client;
  }

  saveClientInformation(client) {
    return this.write('client', client);
  }

  async tokens() {
    return (await this.read()).tokens;
  }

  saveTokens(tokens) {
    const saved = Number.isFinite(tokens.expires_in)
      ? { ...tokens, expires_at: Date.now() + tokens.expires_in * 1000 }
      : tokens;
    return this.write('tokens', saved);
  }

  async codeVerifier() {
    return (await this.read()).codeVerifier;
  }

  saveCodeVerifier(codeVerifier) {
    return this.write('codeVerifier', codeVerifier);
  }

  redirectToAuthorization(url) {
    console.log(url.toString());
    const command = process.platform === 'darwin' ? 'open' : 'xdg-open';
    spawn(command, [url.toString()], { detached: true, stdio: 'ignore' })
      .on('error', () => {})
      .unref();
  }
}

async function mcpUrl() {
  let value = process.env.MCP_URL;
  if (!value) {
    try {
      const contents = await readFile(path.join(evalsDir, '.env'), 'utf8');
      for (const line of contents.split(/\r?\n/)) {
        const separator = line.indexOf('=');
        if (separator < 0 || line.slice(0, separator).trim() !== 'MCP_URL') continue;
        value = line.slice(separator + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
        break;
      }
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
    }
  }
  if (!value) throw new Error('MCP_URL is required in the environment or evals/.env');
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('MCP_URL must use http or https');
  return url;
}

async function callbackServer() {
  let resolveCode;
  let rejectCode;
  const code = new Promise((resolve, reject) => {
    resolveCode = resolve;
    rejectCode = reject;
  });
  code.catch(() => {});

  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname !== '/callback') {
      response.writeHead(404).end();
      return;
    }
    response.setHeader('Content-Type', 'text/plain; charset=utf-8');
    const error = url.searchParams.get('error');
    const authorizationCode = url.searchParams.get('code');
    if (error || !authorizationCode) {
      response.statusCode = 400;
      response.end('Login failed; return to the terminal.');
      rejectCode(new Error(url.searchParams.get('error_description') || error || 'Missing authorization code'));
      return;
    }
    response.end('You can close this tab');
    resolveCode(authorizationCode);
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const { port } = server.address();
  return { server, code, redirectUrl: `http://127.0.0.1:${port}/callback` };
}

async function login(serverUrl) {
  const callback = await callbackServer();
  try {
    const provider = new FileOAuthProvider(serverUrl, callback.redirectUrl);
    const result = await auth(provider, { serverUrl, fetchFn });
    if (result === 'AUTHORIZED') {
      console.log('Already logged in; tokens refreshed');
      return;
    }
    if (result !== 'REDIRECT') throw new Error('OAuth login did not redirect');
    const authorizationCode = await callback.code;
    if (await auth(provider, { serverUrl, authorizationCode, fetchFn }) !== 'AUTHORIZED') {
      throw new Error('OAuth login was not authorized');
    }
    console.log(`Logged in; tokens saved to evals/.auth/${serverUrl.hostname}.json`);
  } finally {
    await new Promise((resolve) => callback.server.close(resolve));
  }
}

function noLoginMessage(serverUrl) {
  return `No saved login for ${serverUrl.hostname}. Run: node evals/auth.mjs login`;
}

function printAccessToken(tokens) {
  if (Number.isFinite(tokens.expires_at)) {
    console.error(`Token expires in ${Math.max(0, Math.ceil((tokens.expires_at - Date.now()) / 1000))}s`);
  } else {
    console.error('Token expiry unknown');
  }
  console.log(tokens.access_token);
}

async function token(serverUrl) {
  const provider = new FileOAuthProvider(serverUrl, 'http://127.0.0.1/callback');
  const savedTokens = await provider.tokens();
  if (!savedTokens) throw new Error(noLoginMessage(serverUrl));
  if (validAccessToken(savedTokens)) {
    printAccessToken(savedTokens);
    return;
  }
  provider.redirectToAuthorization = () => {
    throw new Error('needs login');
  };

  try {
    if (await auth(provider, { serverUrl, fetchFn }) !== 'AUTHORIZED') throw new Error('needs login');
    const tokens = await provider.tokens();
    if (!tokens?.access_token) throw new Error('needs login');
    printAccessToken(tokens);
  } catch {
    throw new Error(noLoginMessage(serverUrl));
  }
}

async function main() {
  const command = process.argv[2];
  if (!['login', 'token'].includes(command)) throw new Error('Usage: node evals/auth.mjs <login|token>');
  const serverUrl = await mcpUrl();
  await (command === 'login' ? login(serverUrl) : token(serverUrl));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
