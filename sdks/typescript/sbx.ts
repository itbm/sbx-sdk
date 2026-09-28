// Hand-written convenience wrapper over the Fern-generated SbxClient.
// Preserved across `make generate` via .fernignore.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fetch as undiciFetch, Agent, type Dispatcher } from "undici";
import { SbxClient } from "./index.js";

const execFileAsync = promisify(execFile);

/** Environment variable that overrides socket discovery. */
export const SOCKET_ENV_VAR = "SBX_SOCKET";

/** How long to wait for `sbx daemon status` before giving up, in milliseconds. */
export const DISCOVERY_TIMEOUT_MS = 10_000;

/**
 * Parses the socket path out of `sbx daemon status`.
 *
 * The command prints the path whether or not the daemon is running, and may
 * exit non-zero when it is stopped, so only the output is checked.
 */
export async function discoverSocketPath(command = "sbx", timeoutMs = DISCOVERY_TIMEOUT_MS): Promise<string> {
  let stdout: string;
  let stderr = "";
  let exitCode: number | string = 0;
  try {
    ({ stdout } = await execFileAsync(command, ["daemon", "status"], { timeout: timeoutMs }));
  } catch (err) {
    const failure = err as { code?: number | string; killed?: boolean; stdout?: string; stderr?: string };
    // A numeric code means the command ran and exited non-zero; anything
    // else (ENOENT, a timeout kill) means it didn't run to completion.
    if (typeof failure.code !== "number" || failure.killed) {
      throw new Error(
        `Failed to run \`${command} daemon status\` to discover the socket path (is \`${command}\` installed and on PATH?). ` +
          `Set ${SOCKET_ENV_VAR} or pass socketPath explicitly to createSbxClient({ socketPath: '...' }) instead.`,
        { cause: err },
      );
    }
    stdout = failure.stdout ?? "";
    stderr = failure.stderr ?? "";
    exitCode = failure.code;
  }

  const match = stdout.match(/^Socket:\s*(\S+)/m);
  if (!match) {
    throw new Error(
      `Could not parse a socket path from \`${command} daemon status\` output (exit code ${exitCode}):\n${stdout}${stderr}`,
    );
  }
  return match[1];
}

/** Returns socketPath if given, else $SBX_SOCKET if set, else discovers it via `sbx daemon status`. */
export async function resolveSocketPath(socketPath?: string): Promise<string> {
  if (socketPath) {
    return socketPath;
  }
  const fromEnv = process.env[SOCKET_ENV_VAR];
  if (fromEnv) {
    return fromEnv;
  }
  return discoverSocketPath();
}

export interface CreateSbxClientOptions {
  /** Override the socket path (default: $SBX_SOCKET, else discovered via `sbx daemon status`). */
  socketPath?: string;
  /** No token is sent by default — sbx v0.34.0 doesn't enforce bearerAuth over the local socket. Pass this if a future version does. */
  token?: string;
  /** Like `token`, but called for each request, so it can return a refreshed token. Takes precedence over `token`. */
  getToken?: () => string | Promise<string>;
}

/** An SbxClient that also owns its socket connections. */
export type SbxSocketClient = SbxClient & {
  /** Closes the client's socket connections. Idle keep-alive sockets otherwise keep the process alive for a few seconds. */
  close(): Promise<void>;
};

/** Construct an SbxClient wired to the local daemon socket. */
export async function createSbxClient(opts: CreateSbxClientOptions = {}): Promise<SbxSocketClient> {
  const socketPath = await resolveSocketPath(opts.socketPath);
  const dispatcher: Dispatcher = new Agent({ connect: { socketPath } });
  const getToken = opts.getToken ?? (opts.token !== undefined ? () => opts.token as string : undefined);

  const client = new SbxClient({
    baseUrl: "http://localhost", // host ignored; the socket does the routing
    auth: getToken ? { token: getToken } : false,
    // undici's Response/Request types don't structurally match lib.dom's at
    // the type level, even though they're compatible at runtime (Node's
    // global fetch is undici under the hood).
    fetch: ((input: RequestInfo | URL, init: RequestInit = {}) =>
      undiciFetch(input as string, {
        ...init,
        dispatcher,
        // Required by undici when the body is a stream (e.g. a tar upload).
        ...(isStream(init.body) ? { duplex: "half" } : {}),
      } as never)) as typeof fetch,
  });

  return Object.assign(client, { close: () => dispatcher.close() });
}

function isStream(body: unknown): boolean {
  return (
    body != null &&
    typeof body === "object" &&
    (typeof (body as ReadableStream).getReader === "function" || Symbol.asyncIterator in body)
  );
}
