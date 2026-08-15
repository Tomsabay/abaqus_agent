#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import process from 'node:process';

const DEFAULT_TIMEOUT_MS = 120000;

function parseArgs(argv) {
  const opts = {
    cwd: process.cwd(),
    prompt: '',
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === '--cwd' && next) {
      opts.cwd = next;
      i += 1;
    } else if (arg === '--prompt' && next) {
      opts.prompt = next;
      i += 1;
    } else if (arg === '--timeout-ms' && next) {
      opts.timeoutMs = Number.parseInt(next, 10);
      i += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!opts.prompt.trim()) throw new Error('Missing --prompt');
  return opts;
}

function sanitizeEnv(sourceEnv) {
  const env = { ...sourceEnv };
  for (const key of Object.keys(env)) {
    if (key.startsWith('CLAUDE_CODE_') || key.startsWith('CLAUDE_AGENT_')) {
      delete env[key];
    }
  }
  return env;
}

function resolveCodexSpawn() {
  // Windows spawn() does not consult PATHEXT (ENOENT for the npm "codex" .cmd
  // shim) and Node >=18.20 refuses to spawn .cmd files without shell:true
  // (EINVAL, CVE-2024-27980). Bypass the shim: run codex.js with this node.
  if (process.platform !== 'win32') return { command: 'codex', prefixArgs: [] };
  for (const dir of (process.env.PATH || '').split(';')) {
    if (!dir) continue;
    const shimTarget = join(dir, 'node_modules', '@openai', 'codex', 'bin', 'codex.js');
    if (existsSync(shimTarget)) {
      return { command: process.execPath, prefixArgs: [shimTarget] };
    }
    if (existsSync(join(dir, 'codex.exe'))) {
      return { command: join(dir, 'codex.exe'), prefixArgs: [] };
    }
  }
  return { command: 'codex', prefixArgs: [] };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const codex = resolveCodexSpawn();
  const proc = spawn(codex.command, [...codex.prefixArgs, 'app-server', '--stdio'], {
    cwd: opts.cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: sanitizeEnv(process.env),
  });

  let nextId = 0;
  let threadId = null;
  let turnId = null;
  let completedTurn = null;
  let assistantText = '';
  let stderrText = '';
  let settled = false;
  const pending = new Map();
  const notifications = new Map();

  const timeout = setTimeout(() => {
    fail(new Error(`Timed out after ${opts.timeoutMs}ms`));
  }, opts.timeoutMs);

  const send = (message) => {
    if (!settled) proc.stdin.write(`${JSON.stringify(message)}\n`);
  };

  const request = (method, params) => {
    const id = nextId;
    nextId += 1;
    const promise = new Promise((resolve, reject) => {
      pending.set(id, { method, resolve, reject });
    });
    send(params === undefined ? { method, id } : { method, id, params });
    return promise;
  };

  const rejectServerRequest = (message) => {
    if (message.method === 'item/commandExecution/requestApproval') {
      send({ id: message.id, result: { decision: 'decline' } });
      return;
    }
    if (message.method === 'item/fileChange/requestApproval') {
      send({ id: message.id, result: { decision: 'decline' } });
      return;
    }
    send({
      id: message.id,
      error: { code: -32000, message: `Unhandled request: ${message.method}` },
    });
  };

  const stdout = createInterface({ input: proc.stdout });
  stdout.on('line', (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch (err) {
      fail(new Error(`Invalid JSON from app-server: ${err.message}`));
      return;
    }
    if (message.id !== undefined && pending.has(message.id)) {
      const waiter = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) {
        waiter.reject(new Error(`${waiter.method} failed: ${message.error.message || JSON.stringify(message.error)}`));
      } else {
        waiter.resolve(message.result);
      }
      return;
    }
    if (message.id !== undefined && message.method) {
      rejectServerRequest(message);
      return;
    }
    if (!message.method) return;
    notifications.set(message.method, (notifications.get(message.method) || 0) + 1);
    if (message.method === 'turn/started') {
      turnId = message.params?.turn?.id || turnId;
    } else if (message.method === 'item/agentMessage/delta') {
      assistantText += message.params?.delta || '';
    } else if (message.method === 'item/completed') {
      const item = message.params?.item;
      if (item?.type === 'agentMessage' && item.text && !assistantText.includes(item.text)) {
        assistantText += item.text;
      }
    } else if (message.method === 'turn/completed') {
      completedTurn = message.params?.turn || null;
      if (pending.has('turn/completed')) {
        pending.get('turn/completed').resolve();
        pending.delete('turn/completed');
      }
    } else if (message.method === 'error') {
      fail(new Error(message.params?.message || JSON.stringify(message.params)));
    }
  });

  proc.stderr.on('data', (chunk) => {
    stderrText += chunk.toString();
  });

  proc.on('error', fail);
  proc.on('close', (code, signal) => {
    if (!settled) fail(new Error(`app-server exited before completion: code=${code} signal=${signal}`));
  });

  try {
    const initialize = await request('initialize', {
      clientInfo: {
        name: 'abaqus_agent_copilot',
        title: 'Abaqus Agent Copilot',
        version: '0.1.0',
      },
      capabilities: { experimentalApi: true },
    });
    send({ method: 'initialized', params: {} });

    const threadResult = await request('thread/start', {
      cwd: opts.cwd,
      runtimeWorkspaceRoots: [opts.cwd],
      approvalPolicy: 'never',
      sandbox: 'read-only',
      ephemeral: true,
      threadSource: 'user',
    });
    threadId = threadResult?.thread?.id;
    if (!threadId) throw new Error(`thread/start did not return thread.id`);

    const turnResult = await request('turn/start', {
      threadId,
      cwd: opts.cwd,
      runtimeWorkspaceRoots: [opts.cwd],
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'readOnly', networkAccess: false },
      input: [{ type: 'text', text: opts.prompt, text_elements: [] }],
    });
    turnId = turnResult?.turn?.id || null;

    if (!completedTurn) {
      await new Promise((resolve, reject) => {
        pending.set('turn/completed', { method: 'turn/completed', resolve, reject });
      });
    }
    if (!completedTurn || completedTurn.status !== 'completed') {
      throw new Error(`Turn did not complete successfully`);
    }
    finish({
      ok: true,
      initialize,
      threadId,
      turnId: completedTurn.id || turnId,
      assistantText: assistantText.trim(),
      notifications: Object.fromEntries(notifications.entries()),
    });
  } catch (err) {
    fail(err);
  }

  function finish(result) {
    settled = true;
    clearTimeout(timeout);
    stdout.close();
    proc.stdin.end();
    proc.kill('SIGTERM');
    console.log(JSON.stringify(result));
  }

  function fail(error) {
    if (settled) return;
    settled = true;
    clearTimeout(timeout);
    for (const waiter of pending.values()) waiter.reject?.(error);
    pending.clear();
    stdout.close();
    proc.stdin.end();
    proc.kill('SIGTERM');
    console.error(JSON.stringify({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      threadId,
      turnId,
      assistantText: assistantText.trim(),
      stderrTail: stderrText.trim().split('\n').slice(-8).join('\n'),
      notifications: Object.fromEntries(notifications.entries()),
    }));
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(JSON.stringify({ ok: false, error: err.message }));
  process.exitCode = 1;
});
