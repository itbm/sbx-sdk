// Tests for the hand-written sbx.ts wrapper, run with `node --test` against
// the compiled dist/. The smoke tests use the generated client over a real
// Unix socket against tests/fixtures/fake_sbxd.py at the repo root; discovery
// is tested against tests/fixtures/fake-sbx.

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SOCKET_ENV_VAR,
  createSbxClient,
  discoverSocketPath,
  resolveSocketPath,
} from "../dist/sbx.js";

const fixtures = resolve(dirname(fileURLToPath(import.meta.url)), "../../../tests/fixtures");
const fakeSbx = join(fixtures, "fake-sbx");
const fakeSbxd = join(fixtures, "fake_sbxd.py");

function withEnv(vars, fn) {
  const saved = Object.fromEntries(Object.keys(vars).map((k) => [k, process.env[k]]));
  Object.assign(process.env, vars);
  const restore = () => {
    for (const [k, v] of Object.entries(saved)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  };
  return Promise.resolve().then(fn).finally(restore);
}

// ── Socket discovery ─────────────────────────────────────────────────────────

test("discover parses the Socket line", () =>
  withEnv({ FAKE_SBX_SOCKET: "/run/sbx/sandboxd.sock" }, async () => {
    assert.equal(await discoverSocketPath(fakeSbx), "/run/sbx/sandboxd.sock");
  }));

test("discover tolerates a non-zero exit", () =>
  withEnv({ FAKE_SBX_SOCKET: "/run/sbx/sandboxd.sock", FAKE_SBX_EXIT: "1" }, async () => {
    assert.equal(await discoverSocketPath(fakeSbx), "/run/sbx/sandboxd.sock");
  }));

test("discover fails without a Socket line", () =>
  withEnv({ FAKE_SBX_NO_SOCKET: "1" }, async () => {
    await assert.rejects(discoverSocketPath(fakeSbx), /Could not parse a socket path/);
  }));

test("discover fails when the command is missing", async () => {
  await assert.rejects(discoverSocketPath("/nonexistent/sbx"), /is `\/nonexistent\/sbx` installed/);
});

test("discover times out", async () => {
  const dir = mkdtempSync("/tmp/sbx-");
  const slow = join(dir, "slow-sbx");
  writeFileSync(slow, "#!/bin/sh\nexec sleep 5\n", { mode: 0o755 });
  try {
    await assert.rejects(discoverSocketPath(slow, 300), /Failed to run/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("resolve prefers explicit path, then env var, then the CLI", async () => {
  await withEnv({ [SOCKET_ENV_VAR]: "/from/env.sock" }, async () => {
    assert.equal(await resolveSocketPath("/explicit.sock"), "/explicit.sock");
    assert.equal(await resolveSocketPath(), "/from/env.sock");
  });

  const bin = mkdtempSync("/tmp/sbx-");
  symlinkSync(fakeSbx, join(bin, "sbx"));
  try {
    await withEnv(
      { [SOCKET_ENV_VAR]: "", PATH: `${bin}:${process.env.PATH}`, FAKE_SBX_SOCKET: "/from/cli.sock" },
      async () => assert.equal(await resolveSocketPath(), "/from/cli.sock"),
    );
  } finally {
    rmSync(bin, { recursive: true, force: true });
  }
});

// ── Smoke tests over the socket ──────────────────────────────────────────────

const daemons = [];

async function startDaemon(...extraArgs) {
  const dir = mkdtempSync("/tmp/sbx-");
  const socketPath = join(dir, "sbxd.sock");
  const proc = spawn("python3", [fakeSbxd, socketPath, ...extraArgs], { stdio: ["ignore", "pipe", "inherit"] });
  daemons.push({ proc, dir });
  const [chunk] = await once(proc.stdout, "data");
  assert.equal(chunk.toString(), "ready\n");
  return socketPath;
}

let socketPath;
before(async () => {
  socketPath = await startDaemon();
});
after(() => {
  for (const { proc, dir } of daemons) {
    proc.kill();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("health and list over the socket", async () => {
  const client = await createSbxClient({ socketPath });
  try {
    const health = await client.daemon.getDaemonHealth();
    assert.equal(health.status, "healthy");
    const sandboxes = await client.sandboxes.listSandboxes();
    assert.deepEqual(
      sandboxes.map((s) => s.name),
      ["claude-demo"],
    );
  } finally {
    await client.close();
  }
});

test("socket from the env var", () =>
  withEnv({ [SOCKET_ENV_VAR]: socketPath }, async () => {
    const client = await createSbxClient();
    try {
      assert.equal((await client.daemon.getDaemonHealth()).status, "healthy");
    } finally {
      await client.close();
    }
  }));

test("token is sent", async () => {
  const tokenSocket = await startDaemon("--token", "s3cret");
  const without = await createSbxClient({ socketPath: tokenSocket });
  const withToken = await createSbxClient({ socketPath: tokenSocket, token: "s3cret" });
  const withGetter = await createSbxClient({ socketPath: tokenSocket, getToken: async () => "s3cret" });
  try {
    await assert.rejects(without.sandboxes.listSandboxes());
    assert.equal((await withToken.sandboxes.listSandboxes()).length, 1);
    assert.equal((await withGetter.sandboxes.listSandboxes()).length, 1);
  } finally {
    await Promise.all([without.close(), withToken.close(), withGetter.close()]);
  }
});
