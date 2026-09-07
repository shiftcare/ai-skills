import { query } from '@anthropic-ai/claude-agent-sdk';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const readTools = new Set(JSON.parse(readFileSync(new URL('../read_tools.json', import.meta.url)))
  .map((name) => `mcp__shiftcare__${name}`));

// Local calendar date, matching what the agent's own environment reports.
const localDate = () => new Date().toLocaleDateString('en-CA');

export function captureToolTrace(message, state) {
  if (message.type === 'assistant') {
    for (const block of message.message.content) {
      if (block.type !== 'tool_use') continue;
      const call = {
        name: block.name.replace(/^mcp__.+?__/, ''),
        input: block.input,
        output: null,
        isError: false,
      };
      state.toolCalls.push(call);
      state.callsById.set(block.id, call);
    }
    return;
  }

  if (message.type !== 'user' || !Array.isArray(message.message.content)) return;
  const results = message.message.content.filter((block) => block.type === 'tool_result');
  for (const block of results) {
    const call = state.callsById.get(block.tool_use_id);
    if (!call) continue;
    call.output = results.length === 1 && message.tool_use_result !== undefined
      ? message.tool_use_result
      : block.content;
    call.isError = block.is_error === true;
  }
}

export async function runClaude({ prompt, model, cwd, skill, mcp }) {
  if (typeof prompt !== 'string' || typeof model !== 'string' || typeof cwd !== 'string') {
    throw new Error('prompt, model, and cwd must be strings');
  }
  if (mcp && (typeof mcp.url !== 'string' || typeof mcp.token !== 'string')) {
    throw new Error('mcp.url and mcp.token must be strings');
  }

  const state = { toolCalls: [], callsById: new Map() };
  const options = {
    model,
    cwd,
    persistSession: false,
    settingSources: ['project'],
    skills: skill ? [skill] : [],
    maxTurns: mcp ? 10 : 1,
    // Skill is the built-in that loads a skill's body on demand; without it skills is inert.
    tools: mcp ? ['Skill'] : [],
    // Without this, the SDK also loads the user's claude.ai connectors.
    strictMcpConfig: true,
    systemPrompt: mcp
      ? `You are a helpful assistant for a ShiftCare care-management account. Today's date is ${localDate()}. Use the available tools to answer the user's question.`
      : 'Answer the evaluation prompt directly. Return only the requested output.',
    ...(mcp ? {
      // Run before permissions so project allow rules cannot approve MCP writes.
      hooks: { PreToolUse: [{ matcher: '^mcp__', hooks: [async ({ tool_name }) => ({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: readTools.has(tool_name) ? 'allow' : 'deny',
          permissionDecisionReason: 'Evaluations permit only the supported read tools.',
        },
      })] }] },
      mcpServers: {
        shiftcare: {
          type: 'http',
          url: mcp.url,
          headers: { Authorization: `Bearer ${mcp.token}` },
        },
      },
    } : {}),
  };

  for await (const message of query({ prompt, options })) {
    captureToolTrace(message, state);
    if (message.type !== 'result') continue;
    if (message.subtype !== 'success') throw new Error(`Claude agent failed: ${message.subtype}`);
    if (message.terminal_reason && message.terminal_reason !== 'completed') {
      throw new Error(`Claude agent stopped: ${message.terminal_reason}`);
    }
    return {
      answer: message.result,
      toolCalls: state.toolCalls,
      usage: {
        inputTokens: message.usage.input_tokens
          + message.usage.cache_creation_input_tokens
          + message.usage.cache_read_input_tokens,
        outputTokens: message.usage.output_tokens,
        costUsd: message.total_cost_usd,
      },
      durationMs: message.duration_ms,
      turns: message.num_turns,
    };
  }

  throw new Error('Claude agent returned no result');
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  process.stdout.write(JSON.stringify(await runClaude(JSON.parse(input))));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
