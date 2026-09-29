# Hand-written convenience wrapper over the Fern-generated Sbx client.
# Preserved across `make generate` via .fernignore.

from __future__ import annotations

import os
import re
import subprocess
from typing import Callable, Optional, Union

import httpx

from .client import AsyncSbx, Sbx

_SOCKET_STATUS_RE = re.compile(r"^Socket:\s*(\S+)", re.MULTILINE)

#: Environment variable that overrides socket discovery.
SOCKET_ENV_VAR = "SBX_SOCKET"

#: How long to wait for `sbx daemon status` before giving up, in seconds.
DISCOVERY_TIMEOUT = 10.0

Token = Union[str, Callable[[], str]]


def discover_socket_path(command: str = "sbx", timeout: float = DISCOVERY_TIMEOUT) -> str:
    """
    Parses the socket path out of `sbx daemon status`.

    The command prints the path whether or not the daemon is running, and may
    exit non-zero when it is stopped, so only the output is checked.
    """
    try:
        result = subprocess.run(
            [command, "daemon", "status"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Failed to run `{command} daemon status` to discover the socket path "
            f"(is `{command}` installed and on PATH?). Set {SOCKET_ENV_VAR} or pass "
            "socket_path explicitly to create_sbx_client() instead."
        ) from exc

    match = _SOCKET_STATUS_RE.search(result.stdout)
    if not match:
        raise RuntimeError(
            f"Could not parse a socket path from `{command} daemon status` output "
            f"(exit code {result.returncode}):\n{result.stdout}{result.stderr}"
        )
    return match.group(1)


def resolve_socket_path(socket_path: Optional[str] = None) -> str:
    """Returns socket_path if given, else $SBX_SOCKET if set, else discovers it via `sbx daemon status`."""
    if socket_path:
        return socket_path
    from_env = os.environ.get(SOCKET_ENV_VAR)
    if from_env:
        return from_env
    return discover_socket_path()


def create_sbx_client(
    socket_path: Optional[str] = None,
    *,
    token: Optional[Token] = None,
    timeout: float = 60,
) -> Sbx:
    """
    Construct an Sbx client wired to the local daemon's unix socket.

    The socket is resolved by resolve_socket_path(). No token is sent unless
    given: sbx v0.34.0 doesn't enforce bearerAuth over the local socket.
    token may be a string or a callable that returns a fresh one per request.

    Call close_sbx_client() when done to release the socket connections.
    """
    transport = httpx.HTTPTransport(uds=resolve_socket_path(socket_path))
    httpx_client = httpx.Client(transport=transport, timeout=timeout)
    return Sbx(base_url="http://localhost", token=token, httpx_client=httpx_client)


def create_async_sbx_client(
    socket_path: Optional[str] = None,
    *,
    token: Optional[Token] = None,
    timeout: float = 60,
) -> AsyncSbx:
    """Async counterpart of create_sbx_client(), returning an AsyncSbx."""
    transport = httpx.AsyncHTTPTransport(uds=resolve_socket_path(socket_path))
    httpx_client = httpx.AsyncClient(transport=transport, timeout=timeout)
    return AsyncSbx(base_url="http://localhost", token=token, httpx_client=httpx_client)


def close_sbx_client(client: Sbx) -> None:
    """Closes the connections held by a client from create_sbx_client()."""
    client._client_wrapper.httpx_client.httpx_client.close()


async def aclose_sbx_client(client: AsyncSbx) -> None:
    """Closes the connections held by a client from create_async_sbx_client()."""
    await client._client_wrapper.httpx_client.httpx_client.aclose()
