"""Tests for the hand-written sbx.py wrapper.

The smoke tests run the generated client over a real Unix socket against
tests/fixtures/fake_sbxd.py. Socket discovery is tested against
tests/fixtures/fake-sbx, which mimics `sbx daemon status`.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from sbx_sdk.errors import NotFoundError, UnauthorizedError
from sbx_sdk.sbx import (
    SOCKET_ENV_VAR,
    aclose_sbx_client,
    close_sbx_client,
    create_async_sbx_client,
    create_sbx_client,
    discover_socket_path,
    resolve_socket_path,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
FAKE_SBX = str(FIXTURES / "fake-sbx")
FAKE_SBXD = str(FIXTURES / "fake_sbxd.py")


@pytest.fixture
def short_tmp():
    # Unix socket paths are limited to ~104 bytes, so avoid pytest's long tmp_path.
    path = tempfile.mkdtemp(prefix="sbx-", dir="/tmp")
    yield Path(path)
    shutil.rmtree(path, ignore_errors=True)


def start_daemon(socket_path, token=None):
    args = [sys.executable, FAKE_SBXD, str(socket_path)]
    if token:
        args += ["--token", token]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "ready"
    return proc


@pytest.fixture
def daemon(short_tmp):
    socket_path = short_tmp / "sbxd.sock"
    proc = start_daemon(socket_path)
    yield socket_path
    proc.terminate()
    proc.wait()


@pytest.fixture
def token_daemon(short_tmp):
    socket_path = short_tmp / "sbxd.sock"
    proc = start_daemon(socket_path, token="s3cret")
    yield socket_path
    proc.terminate()
    proc.wait()


# ── Socket discovery ──────────────────────────────────────────────────────────


def test_discover_parses_socket_line(monkeypatch):
    monkeypatch.setenv("FAKE_SBX_SOCKET", "/run/sbx/sandboxd.sock")
    assert discover_socket_path(FAKE_SBX) == "/run/sbx/sandboxd.sock"


def test_discover_tolerates_non_zero_exit(monkeypatch):
    # A stopped daemon still prints the socket path.
    monkeypatch.setenv("FAKE_SBX_SOCKET", "/run/sbx/sandboxd.sock")
    monkeypatch.setenv("FAKE_SBX_EXIT", "1")
    assert discover_socket_path(FAKE_SBX) == "/run/sbx/sandboxd.sock"


def test_discover_fails_without_socket_line(monkeypatch):
    monkeypatch.setenv("FAKE_SBX_NO_SOCKET", "1")
    with pytest.raises(RuntimeError, match="Could not parse a socket path"):
        discover_socket_path(FAKE_SBX)


def test_discover_fails_when_command_missing():
    with pytest.raises(RuntimeError, match="is `/nonexistent/sbx` installed"):
        discover_socket_path("/nonexistent/sbx")


def test_discover_times_out(short_tmp):
    slow = short_tmp / "slow-sbx"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    slow.chmod(0o755)
    with pytest.raises(RuntimeError, match="Failed to run"):
        discover_socket_path(str(slow), timeout=0.3)


def test_resolve_prefers_explicit_path(monkeypatch):
    monkeypatch.setenv(SOCKET_ENV_VAR, "/from/env.sock")
    assert resolve_socket_path("/explicit.sock") == "/explicit.sock"


def test_resolve_uses_env_var(monkeypatch):
    monkeypatch.setenv(SOCKET_ENV_VAR, "/from/env.sock")
    assert resolve_socket_path() == "/from/env.sock"


def test_resolve_falls_back_to_cli(monkeypatch, short_tmp):
    (short_tmp / "sbx").symlink_to(FAKE_SBX)
    monkeypatch.setenv("PATH", f"{short_tmp}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv(SOCKET_ENV_VAR, raising=False)
    monkeypatch.setenv("FAKE_SBX_SOCKET", "/from/cli.sock")
    assert resolve_socket_path() == "/from/cli.sock"


# ── Smoke tests over the socket ───────────────────────────────────────────────


def test_health_list_and_exec(daemon):
    client = create_sbx_client(str(daemon))
    try:
        health = client.daemon.get_daemon_health()
        assert health.status == "healthy"
        assert health.version == "v0.34.0"

        sandboxes = client.sandboxes.list_sandboxes()
        assert [s.name for s in sandboxes] == ["claude-demo"]

        output = client.exec.in_sandbox("claude-demo", cmd=["echo", "hi"])
        assert output == "echo hi\n"
    finally:
        close_sbx_client(client)


def test_typed_not_found_error(daemon):
    client = create_sbx_client(str(daemon))
    try:
        with pytest.raises(NotFoundError):
            client.exec.in_sandbox("missing", cmd=["true"])
    finally:
        close_sbx_client(client)


def test_socket_from_env_var(daemon, monkeypatch):
    monkeypatch.setenv(SOCKET_ENV_VAR, str(daemon))
    client = create_sbx_client()
    try:
        assert client.daemon.get_daemon_health().status == "healthy"
    finally:
        close_sbx_client(client)


def test_token_is_sent(token_daemon):
    without = create_sbx_client(str(token_daemon))
    with_token = create_sbx_client(str(token_daemon), token="s3cret")
    with_callable = create_sbx_client(str(token_daemon), token=lambda: "s3cret")
    try:
        # Health needs no token either way.
        assert without.daemon.get_daemon_health().status == "healthy"
        with pytest.raises(UnauthorizedError):
            without.sandboxes.list_sandboxes()
        assert len(with_token.sandboxes.list_sandboxes()) == 1
        assert len(with_callable.sandboxes.list_sandboxes()) == 1
    finally:
        for client in (without, with_token, with_callable):
            close_sbx_client(client)


def test_async_client(daemon):
    async def run():
        client = create_async_sbx_client(str(daemon))
        try:
            health = await client.daemon.get_daemon_health()
            output = await client.exec.in_sandbox("claude-demo", cmd=["ls"])
            return health.status, output
        finally:
            await aclose_sbx_client(client)

    assert asyncio.run(run()) == ("healthy", "ls\n")
