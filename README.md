# sbx-sdk

Multi-language client SDKs for the **`sbx` daemon HTTP API** — the local control plane behind [Docker Sandboxes](https://www.docker.com/) (`docker sbx` / `sandboxd`).

The API surface here was **reverse-engineered** from `docker-sbx` v0.34.0 by tracing its Unix-socket traffic and probing endpoints. This repo captures that surface as an OpenAPI spec and generates typed clients (TypeScript, Python, Go, PHP) from it with [Fern](https://buildwithfern.com).

> ⚠️ **Unofficial.** This project is not affiliated with or endorsed by Docker, Inc. It describes a private, undocumented API that can change without notice between `sbx` releases. Use for automation and experimentation at your own risk.

---

## What is `sbx`?

`sbx` is Docker's sandbox tool for running AI coding agents (Claude, Codex, Copilot, Gemini, …) inside isolated, policy-governed microVMs. The CLI talks to a local daemon (`sandboxd`) over two Unix domain sockets:

| Socket | Purpose |
|--------|---------|
| `sandboxd.sock` | Primary `sbx` REST API — sandbox lifecycle, exec, ports, policy, images |
| `docker.sock` | Docker-compatible API subset used for `exec` and image operations |

This SDK targets the **primary `sandboxd.sock` REST API**.

## What's in this repo

| Path | Description |
|------|-------------|
| [`openapi.yaml`](./openapi.yaml) | OpenAPI 3.0.3 spec for the `sandboxd.sock` REST API — the source of truth for SDK generation |
| [`fern/`](./fern) | Fern configuration (`generators.yml`, `fern.config.json`) |
| [`Makefile`](./Makefile) | `make generate`, `make test` and friends |
| `sdks/` | Generated SDK output (git-ignored) plus the hand-written wrappers, packaging files and tests |
| [`tests/fixtures/`](./tests/fixtures) | A fake daemon and a fake `sbx` CLI that the SDK tests run against |

## Generated SDKs

Fern produces idiomatic clients for four languages, configured in [`fern/generators.yml`](./fern/generators.yml):

| Language | Output | Package / module |
|----------|--------|------------------|
| TypeScript | `sdks/typescript` | namespace `Sbx` |
| Python | `sdks/python` | `sbx_sdk` (client `Sbx`) |
| Go | `sdks/go` | `github.com/itbm/sbx-sdk/sdks/go` |
| PHP | `sdks/php` | `itbm/sbx-sdk` (namespace `Sbx`) |

> **Transport note:** the `sbx` API is served over a **Unix domain socket**, not TCP — the host in each URL is ignored. Generated clients point at `http://localhost` and require a custom HTTP transport that dials the socket. Each language has a hand-written wrapper (`sbx.ts` / `sbx.go` / `sbx.py` / `SbxClientFactory.php`) that wires this up automatically — see [Installation](#installation) below.

### Finding the socket

Every wrapper looks for the socket in the same order:

1. The socket path you pass in explicitly.
2. The `SBX_SOCKET` environment variable.
3. The `Socket:` line printed by `sbx daemon status` (which works whether or not the daemon is running). This needs `sbx` on `PATH` and gives up after 10 seconds.

## Installation

Each [GitHub Release](https://github.com/itbm/sbx-sdk/releases) publishes a source tarball per language (built by [`.github/workflows/release.yml`](./.github/workflows/release.yml)), installable directly from the release URL — no registry needed. Replace `X.Y.Z` / `vX.Y.Z` below with an actual [released version](https://github.com/itbm/sbx-sdk/releases); each install pins to that exact URL, so upgrading means bumping the version yourself rather than a semver-range `update`.

### TypeScript

```bash
npm install https://github.com/itbm/sbx-sdk/releases/download/vX.Y.Z/sbx-sdk-typescript-X.Y.Z.tgz
```

```ts
import { createSbxClient } from "sbx-sdk/sbx";

const client = await createSbxClient(); // or { socketPath, token, getToken }
const health = await client.daemon.getDaemonHealth();
await client.close(); // release the socket connections
```

Requires Node.js 22.19 or later.

### Python

```bash
pip install https://github.com/itbm/sbx-sdk/releases/download/vX.Y.Z/sbx-sdk-python-X.Y.Z.tar.gz
```

```python
from sbx_sdk.sbx import close_sbx_client, create_sbx_client

client = create_sbx_client()  # or create_sbx_client(socket_path, token=..., timeout=...)
health = client.daemon.get_daemon_health()
close_sbx_client(client)
```

`create_async_sbx_client()` and `aclose_sbx_client()` do the same for the async client. Requires Python 3.9 or later.

### Go

Go modules resolve straight from this repo's `sdks/go` subdirectory via its own nested tag — no tarball needed:

```bash
go get github.com/itbm/sbx-sdk/sdks/go@vX.Y.Z
```

```go
import sbx "github.com/itbm/sbx-sdk/sdks/go/sbx"

client, err := sbx.NewClient(ctx, "") // "" resolves the socket; add option.WithToken(...) if needed
health, err := client.Daemon.GetDaemonHealth(ctx)
```

The release workflow commits the generated Go code on a commit that isn't on any branch, and tags that commit `sdks/go/vX.Y.Z`. `go get` therefore gets a complete module, while `main` holds only the hand-written wrapper.

### PHP

Composer doesn't resolve arbitrary tarball URLs through `require` alone — point it at the release asset with a [`package` repository](https://getcomposer.org/doc/05-repositories.md#package-2):

```json
{
  "repositories": [
    {
      "type": "package",
      "package": {
        "name": "itbm/sbx-sdk",
        "version": "X.Y.Z",
        "dist": {
          "url": "https://github.com/itbm/sbx-sdk/releases/download/vX.Y.Z/sbx-sdk-php-X.Y.Z.tar.gz",
          "type": "tar"
        }
      }
    }
  ],
  "require": {
    "itbm/sbx-sdk": "X.Y.Z"
  }
}
```

```bash
composer install
```

```php
use Sbx\SbxClientFactory;

$client = SbxClientFactory::create(); // or create($socketPath, token: '...', timeout: 60.0)
$health = $client->daemon->getDaemonHealth();
```

## Generating the SDKs

Releases (tarballs + tags, including the Go nested-module tag) are built automatically by [`.github/workflows/release.yml`](./.github/workflows/release.yml) on every `vX.Y.Z` tag push, after the full test suite passes. [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs the same tests on every push and pull request. The steps below are for local generation.

**Prerequisites**

- Node.js 22 and Docker (Fern's `--local` mode runs each generator in a container)
- `npm ci` to install the pinned Fern CLI (see [`package.json`](./package.json))
- The language toolchains for any SDK you want to build or test: Node.js 22.19+, Python 3.9+, Go, and PHP 8.3+ with Composer

**Generate**

```bash
make check      # validate the spec
make generate   # fern generate --local --force, writing fresh clients into sdks/
make fix-perms  # on Linux, hand back any root-owned files the containers wrote
```

**Test**

```bash
make test       # or test-typescript / test-python / test-go / test-php
```

Each SDK's tests check socket discovery against a fake `sbx` CLI, then make real requests over a Unix socket to a fake daemon ([`tests/fixtures/`](./tests/fixtures)).

**Clean**

```bash
make clean
```

Removes the generated (git-ignored) files under `sdks/`, keeping the committed wrappers, packaging files and tests.

## API at a glance

The `sandboxd.sock` API is grouped as:

| Group | Endpoints | Maps to |
|-------|-----------|---------|
| **Daemon** | `/daemon/health`, `/daemon/info`, `/daemon/diagnostics`, `/daemon/loglevel` | `sbx diagnose` |
| **Sandboxes** | `GET/POST /sandbox`, `/sandbox/{name}` `stop` · `start` · `exec` · `logs` · `save` | `sbx ls` / `create` / `run` / `exec` / `stop` / `rm` |
| **Ports** | `/sandbox/{name}/ports`, `.../ports/unpublish` | `sbx ports` |
| **Runtimes** | `/runtime/{name}/session`, `POST /runtime` | session lookups, re-attach |
| **Policies** | `/policy/setup`, `/policy/rules`, `/policy/profiles`, `/network/log` | `sbx policy …` |
| **Images** | `/docker/images`, `.../create`, `.../load`, `.../remove` | `sbx template …` |

### Text responses

A few endpoints return text rather than JSON, and the SDK methods return it as a string:

- **Exec** (`POST /sandbox/{name}/exec`, non-interactive): the command's combined stdout and stderr.
- **Logs** (`GET /sandbox/{name}/logs`): newline-delimited log lines.
- **Image pull** (`POST /docker/images/create`): newline-delimited JSON progress events, in the same format as `docker pull`. Split the string on newlines and parse each line.

Interactive or TTY exec takes over the HTTP connection for raw streams, which the generated clients can't handle.

### Authentication

The spec marks every endpoint **except** `GET /daemon/health` and `GET /daemon/info` as needing a bearer token. In practice, `sbx` v0.34.0 doesn't enforce this over the local socket, so the wrappers send no token by default. Each accepts one if a future version starts to check:

```bash
SOCK="$HOME/.local/state/sandboxes/sandboxes/sandboxd/sandboxd.sock"

# Health check (no auth)
curl --unix-socket "$SOCK" http://localhost/daemon/health

# Authenticated list
curl --unix-socket "$SOCK" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost/sandbox
```

The token is the Docker OAuth **access token** stored by `sbx login` — a short-lived JWT (~15-minute TTL) that `sbx` refreshes automatically from its stored refresh token. It is persisted **age-encrypted** on disk (under `~/.config/com.docker.sandboxes/`), not in plaintext, so in practice you obtain a live token from an authenticated `sbx` session rather than by reading a file.

> **Tip:** `GET /daemon/health` and `GET /daemon/info` need no auth. `GET /daemon/info` returns the daemon's actual `api_socket` and `docker_socket` paths, which is a reliable way to discover the socket location before making authenticated calls.

## Contributing

1. Update [`openapi.yaml`](./openapi.yaml) as new API behavior is observed.
2. Regenerate with `make generate`.
3. Commit the spec change. Generated code is git-ignored, so only the spec and the hand-written files are committed.

Run `make check`, `make generate` and `make test` before opening a pull request; CI runs the same steps.

Because the API is reverse-engineered, coverage is best-effort — several routes are documented as `501 Not Implemented` upstream (file copy, `save`), and some request/response shapes are inferred rather than confirmed.

## License

Licensed under the [Apache License 2.0](./LICENSE) — Copyright 2026 itbm.

This license covers the contents of this repository (the OpenAPI spec, documentation, and generator configuration). The API it describes is Docker's; this repo only documents and wraps it, and is not affiliated with or endorsed by Docker, Inc.
