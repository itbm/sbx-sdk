<?php

// Hand-written convenience wrapper over the Fern-generated Sbx client.
// Preserved across `make generate` via .fernignore.

namespace Sbx;

use GuzzleHttp\Client as GuzzleClient;
use RuntimeException;

class SbxClientFactory
{
    /** Parses the socket path out of `sbx daemon status`, which prints it whether or not the daemon is running. */
    public static function discoverSocketPath(string $command = 'sbx'): string
    {
        $descriptorSpec = [
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ];
        $process = proc_open([$command, 'daemon', 'status'], $descriptorSpec, $pipes);
        if (!\is_resource($process)) {
            throw new RuntimeException(
                "Failed to run \`$command daemon status\` to discover the socket path " .
                "(is \`$command\` installed and on PATH?). Pass socketPath explicitly " .
                'to SbxClientFactory::create() instead.',
            );
        }

        $stdout = stream_get_contents($pipes[1]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        $exitCode = proc_close($process);

        if ($exitCode !== 0) {
            throw new RuntimeException(
                "Failed to run \`$command daemon status\` to discover the socket path " .
                "(is \`$command\` installed and on PATH?). Pass socketPath explicitly " .
                'to SbxClientFactory::create() instead.',
            );
        }

        if (!preg_match('/^Socket:\s*(\S+)/m', $stdout, $matches)) {
            throw new RuntimeException(
                "Could not parse a socket path from \`$command daemon status\` output:\n$stdout",
            );
        }

        return $matches[1];
    }

    /**
     * Construct an Sbx client wired to the local daemon's unix socket. If
     * $socketPath is null, it is discovered via discoverSocketPath().
     * Requires guzzlehttp/guzzle — CURLOPT_UNIX_SOCKET_PATH is Guzzle-specific,
     * there's no generic PSR-18 way to target a unix socket.
     *
     * No token is set — sbx v0.34.0 doesn't enforce bearerAuth over the local
     * socket. Pass $token to Sbx's constructor directly if a future version does.
     */
    public static function create(?string $socketPath = null): Sbx
    {
        $socketPath ??= self::discoverSocketPath();

        $guzzle = new GuzzleClient([
            'curl' => [\CURLOPT_UNIX_SOCKET_PATH => $socketPath],
        ]);

        return new Sbx(options: [
            'baseUrl' => 'http://localhost',
            'client' => $guzzle,
        ]);
    }
}
