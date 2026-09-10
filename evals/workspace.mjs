import { mkdir, readdir, readlink, symlink, writeFile } from 'node:fs/promises';
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
  const noSkill = path.join(workspaceRoot, 'no-skill');
  const home = path.join(workspaceRoot, 'home');
  const skillNames = (await readdir(path.join(root, 'skills'), { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
  const skills = {};

  await mkdir(noSkill, { recursive: true });
  // Codex reads AGENTS.md from the working directory; this mirrors the Claude runner's system prompt.
  await writeFile(path.join(noSkill, 'AGENTS.md'), `${AGENT_INSTRUCTIONS}\n`);
  for (const skillName of skillNames) {
    const skill = path.join(root, 'skills', skillName);
    const workspace = path.join(workspaceRoot, `with-${skillName}`);
    skills[skillName] = workspace;
    await mkdir(workspace, { recursive: true });
    await writeFile(path.join(workspace, 'AGENTS.md'), `${AGENT_INSTRUCTIONS}\n`);
    await ensureSymlink(skill, path.join(workspace, '.claude', 'skills', skillName), 'dir');
    await ensureSymlink(skill, path.join(workspace, '.agents', 'skills', skillName), 'dir');
  }
  await ensureSymlink(
    path.join(homedir(), '.codex', 'auth.json'),
    path.join(home, '.codex', 'auth.json'),
    'file',
  );

  return { 'no-skill': noSkill, home, skills };
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
