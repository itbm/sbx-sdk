# Hand-written convenience wrapper over the Fern-generated Sbx client.
# Preserved across `make generate` via .fernignore.

import re
import subprocess

import httpx

from .client import Sbx

_SOCKET_STATUS_RE = re.compile(r"^Socket:\s*(\S+)", re.MULTILINE)


def discover_socket_path(command: str = "sbx") -> str:
    """Parses the socket path out of `sbx daemon status`, which prints it whether or not the daemon is running."""
    try:
        result = subprocess.run(
            [command, "daemon", "status"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"Failed to run `{command} daemon status` to discover the socket path "
            f"(is `{command}` installed and on PATH?). Pass socket_path explicitly "
            "to create_sbx_client() instead."
        ) from exc

    match = _SOCKET_STATUS_RE.search(result.stdout)
    if not match:
        raise RuntimeError(
            f"Could not parse a socket path from `{command} daemon status` output:\n{result.stdout}"
        )
    return match.group(1)


def create_sbx_client(socket_path: str | None = None) -> Sbx:
    """
    Construct an Sbx client wired to the local daemon's unix socket. If
    socket_path is omitted, it is discovered via discover_socket_path().

    No token is set — sbx v0.34.0 doesn't enforce bearerAuth over the local
    socket. Pass token=... to the Sbx class directly if a future version does.
    """
    if socket_path is None:
        socket_path = discover_socket_path()

    transport = httpx.HTTPTransport(uds=socket_path)
    httpx_client = httpx.Client(transport=transport, timeout=60)
    return Sbx(base_url="http://localhost", httpx_client=httpx_client)
