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
| [`Makefile`](./Makefile) | `make generate` / `make clean` for SDK generation |
| `sdks/` | Generated SDK output (one directory per language) |

## Generated SDKs

Fern produces idiomatic clients for four languages, configured in [`fern/generators.yml`](./fern/generators.yml):

| Language | Output | Package / module |
|----------|--------|------------------|
| TypeScript | `sdks/typescript` | namespace `Sbx` |
| Python | `sdks/python` | `sbx_sdk` (client `Sbx`) |
| Go | `sdks/go` | `github.com/itbm/sbx-sdk/sdks/go` |
| PHP | `sdks/php` | `itbm/sbx-sdk` (namespace `Sbx`) |

> **Transport note:** the `sbx` API is served over a **Unix domain socket**, not TCP — the host in each URL is ignored. Generated clients point at `http://localhost` and require a custom HTTP transport that dials the socket. Each language has a hand-written wrapper (`sbx.ts` / `sbx.go` / `sbx.py` / `SbxClientFactory.php`) that discovers the socket via `sbx daemon status` and wires this up automatically — see [Installation](#installation) below.

## Installation

Each [GitHub Release](https://github.com/itbm/sbx-sdk/releases) publishes a source tarball per language (built by [`.github/workflows/release.yml`](./.github/workflows/release.yml)), installable directly from the release URL — no registry needed. Replace `X.Y.Z` / `vX.Y.Z` below with an actual [released version](https://github.com/itbm/sbx-sdk/releases); each install pins to that exact URL, so upgrading means bumping the version yourself rather than a semver-range `update`.

### TypeScript

```bash
npm install https://github.com/itbm/sbx-sdk/releases/download/vX.Y.Z/sbx-sdk-typescript-X.Y.Z.tgz
```

```ts
import { createSbxClient } from "sbx-sdk/sbx";

const client = await createSbxClient();
const health = await client.daemon.getDaemonHealth();
```

### Python

```bash
pip install https://github.com/itbm/sbx-sdk/releases/download/vX.Y.Z/sbx-sdk-python-X.Y.Z.tar.gz
```

```python
from sbx_sdk.sbx import create_sbx_client

client = create_sbx_client()
health = client.daemon.get_daemon_health()
```

### Go

Go modules resolve straight from this repo's `sdks/go` subdirectory via its own nested tag — no tarball needed:

```bash
go get github.com/itbm/sbx-sdk/sdks/go@vX.Y.Z
```

```go
import sbx "github.com/itbm/sbx-sdk/sdks/go/sbx"

client, err := sbx.NewClient(ctx, "")
health, err := client.Daemon.GetDaemonHealth(ctx)
```

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

$client = SbxClientFactory::create();
$health = $client->daemon->getDaemonHealth();
```

## Generating the SDKs

Releases (tarballs + tags, including the Go nested-module tag) are built automatically by [`.github/workflows/release.yml`](./.github/workflows/release.yml) on every `vX.Y.Z` tag push. The steps below are for local/manual generation.

**Prerequisites**

- The [Fern CLI](https://buildwithfern.com/learn/cli-api-reference/cli-reference) — `npm install -g fern-api`
- Language toolchains only if you intend to build/run the generated code

**Generate**

```bash
make generate
```

This runs `fern generate --local --force`, writing fresh clients into `sdks/`. (The Makefile uses `sudo` around generation and then restores ownership of the output — Fern's `--local` mode runs generators in Docker.)

**Clean**

```bash
make clean
```

Removes the `sdks/` directory.

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

### Authentication

Every endpoint requires a bearer token **except** `GET /daemon/health` and `GET /daemon/info`:

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
3. Commit the spec change; regenerate SDKs as needed.

Because the API is reverse-engineered, coverage is best-effort — several routes are documented as `501 Not Implemented` upstream (file copy, `save`), and some request/response shapes are inferred rather than confirmed.

## License

Licensed under the [Apache License 2.0](./LICENSE) — Copyright 2026 itbm.

This license covers the contents of this repository (the OpenAPI spec, documentation, and generator configuration). The API it describes is Docker's; this repo only documents and wraps it, and is not affiliated with or endorsed by Docker, Inc.
