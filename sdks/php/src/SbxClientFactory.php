<?php

// Hand-written convenience wrapper over the Fern-generated Sbx client.
// Preserved across `make generate` via .fernignore.

namespace Sbx;

use GuzzleHttp\Client as GuzzleClient;
use RuntimeException;

class SbxClientFactory
{
    /** Environment variable that overrides socket discovery. */
    public const SOCKET_ENV_VAR = 'SBX_SOCKET';

    /** How long to wait for `sbx daemon status` before giving up, in seconds. */
    public const DISCOVERY_TIMEOUT = 10.0;

    /**
     * Parses the socket path out of `sbx daemon status`.
     *
     * The command prints the path whether or not the daemon is running, and
     * may exit non-zero when it is stopped, so only the output is checked.
     */
    public static function discoverSocketPath(string $command = 'sbx', float $timeout = self::DISCOVERY_TIMEOUT): string
    {
        $descriptorSpec = [
            0 => ['file', '/dev/null', 'r'],
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ];
        // proc_open() with an array command doesn't use a shell, so a missing
        // binary shows up as a warning plus a false return; silence the
        // warning and report it ourselves.
        $process = @proc_open([$command, 'daemon', 'status'], $descriptorSpec, $pipes);
        if (!\is_resource($process)) {
            throw new RuntimeException(self::runFailureMessage($command));
        }

        [$stdout, $stderr, $timedOut] = self::readUntilExit($pipes[1], $pipes[2], $timeout);
        if ($timedOut) {
            proc_terminate($process);
        }
        $exitCode = proc_close($process);

        if ($timedOut) {
            throw new RuntimeException(
                "Timed out after {$timeout}s waiting for `$command daemon status`. " . self::overrideHint(),
            );
        }

        if (!preg_match('/^Socket:\s*(\S+)/m', $stdout, $matches)) {
            // 127 is the shell's "command not found"; PHP on some platforms
            // reports a missing binary this way instead of failing proc_open().
            if ($exitCode === 127) {
                throw new RuntimeException(self::runFailureMessage($command));
            }
            throw new RuntimeException(
                "Could not parse a socket path from `$command daemon status` output " .
                "(exit code $exitCode):\n$stdout$stderr",
            );
        }

        return $matches[1];
    }

    /**
     * Returns $socketPath if given, else $SBX_SOCKET if set, else discovers
     * it via `sbx daemon status`.
     */
    public static function resolveSocketPath(?string $socketPath = null): string
    {
        if ($socketPath !== null && $socketPath !== '') {
            return $socketPath;
        }
        $fromEnv = getenv(self::SOCKET_ENV_VAR);
        if (\is_string($fromEnv) && $fromEnv !== '') {
            return $fromEnv;
        }
        return self::discoverSocketPath();
    }

    /**
     * Construct an Sbx client wired to the local daemon's unix socket. The
     * socket is resolved by resolveSocketPath().
     * Requires guzzlehttp/guzzle — CURLOPT_UNIX_SOCKET_PATH is Guzzle-specific,
     * there's no generic PSR-18 way to target a unix socket.
     *
     * No token is sent unless $token is given: sbx v0.34.0 doesn't enforce
     * bearerAuth over the local socket.
     */
    public static function create(?string $socketPath = null, ?string $token = null, float $timeout = 60.0): Sbx
    {
        $guzzle = new GuzzleClient([
            'curl' => [\CURLOPT_UNIX_SOCKET_PATH => self::resolveSocketPath($socketPath)],
            'timeout' => $timeout,
        ]);

        return new Sbx(token: $token, options: [
            'baseUrl' => 'http://localhost',
            'client' => $guzzle,
        ]);
    }

    /**
     * Reads both pipes to EOF, so a chatty stderr can't fill its buffer and
     * block the child, giving up after $timeout seconds.
     *
     * @param resource $stdoutPipe
     * @param resource $stderrPipe
     * @return array{0: string, 1: string, 2: bool} stdout, stderr, timed out
     */
    private static function readUntilExit($stdoutPipe, $stderrPipe, float $timeout): array
    {
        $output = [(int) $stdoutPipe => '', (int) $stderrPipe => ''];
        $open = [$stdoutPipe, $stderrPipe];
        foreach ($open as $pipe) {
            stream_set_blocking($pipe, false);
        }
        $deadline = microtime(true) + $timeout;

        while ($open !== []) {
            $remaining = $deadline - microtime(true);
            if ($remaining <= 0) {
                break;
            }
            $read = $open;
            $write = null;
            $except = null;
            $seconds = (int) $remaining;
            if (stream_select($read, $write, $except, $seconds, (int) (($remaining - $seconds) * 1e6)) === false) {
                break;
            }
            foreach ($read as $pipe) {
                $output[(int) $pipe] .= (string) fread($pipe, 8192);
                if (feof($pipe)) {
                    fclose($pipe);
                    $open = array_filter($open, static fn ($p) => $p !== $pipe);
                }
            }
        }

        $timedOut = $open !== [];
        foreach ($open as $pipe) {
            fclose($pipe);
        }
        return [$output[(int) $stdoutPipe], $output[(int) $stderrPipe], $timedOut];
    }

    private static function runFailureMessage(string $command): string
    {
        return "Failed to run `$command daemon status` to discover the socket path " .
            "(is `$command` installed and on PATH?). " . self::overrideHint();
    }

    private static function overrideHint(): string
    {
        return 'Set ' . self::SOCKET_ENV_VAR . ' or pass $socketPath explicitly to SbxClientFactory::create() instead.';
    }
}
