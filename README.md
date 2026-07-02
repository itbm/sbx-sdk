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
| Go | `sdks/go` | `github.com/itbm/sbx-sdk` |
| PHP | `sdks/php` | `itbm/sbx-sdk` (namespace `Sbx`) |

> **Transport note:** the `sbx` API is served over a **Unix domain socket**, not TCP — the host in each URL is ignored. Generated clients point at `http://localhost` and require a custom HTTP transport that dials the socket at
> `~/.local/state/sandboxes/sandboxes/sandboxd/sandboxd.sock`.

## Generating the SDKs

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
