import { mkdir, readlink, symlink, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const evalsDir = path.dirname(fileURLToPath(import.meta.url));

export const AGENT_INSTRUCTIONS =
  "You are a helpful assistant for a ShiftCare care-management account. Use the available tools to answer the user's question.";

async function ensureSymlink(source, destination, type) {
  await mkdir(path.dirname(destination), { recursive: true });
  const target = path.relative(path.dirname(destination), source);
  try {
    await symlink(target, destination, type);
  } catch (error) {
    if (error?.code !== 'EEXIST' || await readlink(destination) !== target) throw error;
  }
}

export async function ensureWorkspaces(root = path.resolve(evalsDir, '..')) {
  const workspaceRoot = path.join(root, 'evals', '.workspace');
  const withSkill = path.join(workspaceRoot, 'with-skill');
  const noSkill = path.join(workspaceRoot, 'no-skill');
  const home = path.join(workspaceRoot, 'home');
  const skill = path.join(root, 'skills', 'shiftcare-mcp');

  await mkdir(noSkill, { recursive: true });
  // Codex reads AGENTS.md from the working directory; this mirrors the Claude runner's system prompt.
  for (const dir of [withSkill, noSkill]) {
    await mkdir(dir, { recursive: true });
    await writeFile(path.join(dir, 'AGENTS.md'), `${AGENT_INSTRUCTIONS}\n`);
  }
  await ensureSymlink(skill, path.join(withSkill, '.claude', 'skills', 'shiftcare-mcp'), 'dir');
  await ensureSymlink(skill, path.join(withSkill, '.agents', 'skills', 'shiftcare-mcp'), 'dir');
  await ensureSymlink(
    path.join(homedir(), '.codex', 'auth.json'),
    path.join(home, '.codex', 'auth.json'),
    'file',
  );

  return { 'with-skill': withSkill, 'no-skill': noSkill, home };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  ensureWorkspaces().then(
    (workspaces) => console.log(JSON.stringify(workspaces)),
    (error) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    },
  );
}
