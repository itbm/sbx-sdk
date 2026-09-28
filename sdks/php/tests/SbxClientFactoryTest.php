<?php

// Tests for the hand-written SbxClientFactory. The smoke tests run the
// generated client over a real Unix socket against tests/fixtures/fake_sbxd.py
// at the repo root; discovery is tested against tests/fixtures/fake-sbx.

namespace Sbx\Tests;

use PHPUnit\Framework\TestCase;
use RuntimeException;
use Sbx\Exceptions\ItbmApiException;
use Sbx\Exec\Requests\ExecRequest;
use Sbx\SbxClientFactory;

class SbxClientFactoryTest extends TestCase
{
    private const FIXTURES = __DIR__ . '/../../../tests/fixtures';

    /** @var list<resource> */
    private array $daemons = [];

    /** @var list<string> */
    private array $tmpDirs = [];

    protected function tearDown(): void
    {
        foreach ($this->daemons as $daemon) {
            proc_terminate($daemon);
            proc_close($daemon);
        }
        foreach ($this->tmpDirs as $dir) {
            array_map('unlink', glob("$dir/*") ?: []);
            @rmdir($dir);
        }
        foreach (['FAKE_SBX_SOCKET', 'FAKE_SBX_EXIT', 'FAKE_SBX_NO_SOCKET', SbxClientFactory::SOCKET_ENV_VAR] as $var) {
            putenv($var);
        }
    }

    // ── Socket discovery ─────────────────────────────────────────────────────

    public function testDiscoverParsesSocketLine(): void
    {
        putenv('FAKE_SBX_SOCKET=/run/sbx/sandboxd.sock');
        $this->assertSame('/run/sbx/sandboxd.sock', SbxClientFactory::discoverSocketPath(self::FIXTURES . '/fake-sbx'));
    }

    public function testDiscoverToleratesNonZeroExit(): void
    {
        putenv('FAKE_SBX_SOCKET=/run/sbx/sandboxd.sock');
        putenv('FAKE_SBX_EXIT=1');
        $this->assertSame('/run/sbx/sandboxd.sock', SbxClientFactory::discoverSocketPath(self::FIXTURES . '/fake-sbx'));
    }

    public function testDiscoverFailsWithoutSocketLine(): void
    {
        putenv('FAKE_SBX_NO_SOCKET=1');
        $this->expectException(RuntimeException::class);
        $this->expectExceptionMessage('Could not parse a socket path');
        SbxClientFactory::discoverSocketPath(self::FIXTURES . '/fake-sbx');
    }

    public function testDiscoverFailsWhenCommandMissing(): void
    {
        $this->expectException(RuntimeException::class);
        $this->expectExceptionMessage('is `/nonexistent/sbx` installed');
        SbxClientFactory::discoverSocketPath('/nonexistent/sbx');
    }

    public function testResolvePrefersExplicitPathThenEnvVar(): void
    {
        putenv(SbxClientFactory::SOCKET_ENV_VAR . '=/from/env.sock');
        $this->assertSame('/explicit.sock', SbxClientFactory::resolveSocketPath('/explicit.sock'));
        $this->assertSame('/from/env.sock', SbxClientFactory::resolveSocketPath());
    }

    // ── Smoke tests over the socket ──────────────────────────────────────────

    public function testHealthListAndExec(): void
    {
        $client = SbxClientFactory::create($this->startDaemon());

        $this->assertSame('healthy', $client->daemon->getDaemonHealth()->status);
        $sandboxes = $client->sandboxes->listSandboxes();
        $this->assertCount(1, $sandboxes);
        $this->assertSame('claude-demo', $sandboxes[0]->name);
        $this->assertSame(
            "echo hi\n",
            $client->exec->inSandbox('claude-demo', new ExecRequest(['cmd' => ['echo', 'hi']])),
        );
    }

    public function testSocketFromEnvVar(): void
    {
        putenv(SbxClientFactory::SOCKET_ENV_VAR . '=' . $this->startDaemon());
        $this->assertSame('healthy', SbxClientFactory::create()->daemon->getDaemonHealth()->status);
    }

    public function testTokenIsSent(): void
    {
        $socket = $this->startDaemon('s3cret');

        $this->assertCount(1, SbxClientFactory::create($socket, token: 's3cret')->sandboxes->listSandboxes());

        try {
            SbxClientFactory::create($socket)->sandboxes->listSandboxes();
            $this->fail('expected a 401');
        } catch (ItbmApiException $e) {
            $this->assertSame(401, $e->getCode());
        }
    }

    private function startDaemon(?string $token = null): string
    {
        $dir = sys_get_temp_dir() . '/sbx-' . bin2hex(random_bytes(4));
        mkdir($dir);
        $this->tmpDirs[] = $dir;
        $socket = "$dir/sbxd.sock";

        $command = ['python3', self::FIXTURES . '/fake_sbxd.py', $socket];
        if ($token !== null) {
            array_push($command, '--token', $token);
        }
        $daemon = proc_open($command, [1 => ['pipe', 'w']], $pipes);
        $this->assertIsResource($daemon);
        $this->assertSame("ready\n", fgets($pipes[1]));
        $this->daemons[] = $daemon;
        return $socket;
    }
}
