// Hand-written convenience wrapper over the Fern-generated SbxClient.
// Preserved across `make generate` via .fernignore.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fetch as undiciFetch, Agent } from "undici";
import { SbxClient } from "./index.js";

const execFileAsync = promisify(execFile);

/** Parses the socket path out of `sbx daemon status`, which prints it whether or not the daemon is running. */
async function discoverSocketPath(command = "sbx"): Promise<string> {
  let stdout: string;
  try {
    ({ stdout } = await execFileAsync(command, ["daemon", "status"]));
  } catch (err) {
    throw new Error(
      `Failed to run \`${command} daemon status\` to discover the socket path (is \`${command}\` installed and on PATH?). ` +
      "Pass socketPath explicitly to createSbxClient({ socketPath: '...' }) instead.",
      { cause: err },
    );
  }

  const match = stdout.match(/^Socket:\s*(\S+)/m);
  if (!match) {
    throw new Error(`Could not parse a socket path from \`${command} daemon status\` output:\n${stdout}`);
  }
  return match[1];
}

export interface CreateSbxClientOptions {
  /** Override the socket path (default: discovered via `sbx daemon status`). */
  socketPath?: string;
  /** No token is sent by default — sbx v0.34.0 doesn't enforce bearerAuth over the local socket. Pass this if a future version does. */
  getToken?: () => string | Promise<string>;
}

/** Construct an SbxClient wired to the local daemon socket. */
export async function createSbxClient(opts: CreateSbxClientOptions = {}): Promise<SbxClient> {
  const socketPath = opts.socketPath ?? (await discoverSocketPath());
  const dispatcher = new Agent({ connect: { socketPath } });

  return new SbxClient({
    baseUrl: "http://localhost", // host ignored; the socket does the routing
    auth: opts.getToken ? { token: opts.getToken } : false,
    // undici's Response/Request types don't structurally match lib.dom's at
    // the type level, even though they're compatible at runtime (Node's
    // global fetch is undici under the hood).
    fetch: ((input: RequestInfo | URL, init: RequestInit = {}) =>
      undiciFetch(input as string, { ...init, dispatcher } as never)) as typeof fetch,
  });
}
