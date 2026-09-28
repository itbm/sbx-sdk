package sbx

import (
	"bufio"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	option "github.com/itbm/sbx-sdk/sdks/go/option"
)

var fakeSbxd, _ = filepath.Abs("../../../tests/fixtures/fake_sbxd.py")

// startDaemon runs tests/fixtures/fake_sbxd.py on a fresh Unix socket.
func startDaemon(t *testing.T, extraArgs ...string) string {
	t.Helper()
	// Unix socket paths are limited to ~104 bytes, so avoid t.TempDir().
	dir, err := os.MkdirTemp("/tmp", "sbx-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	socket := filepath.Join(dir, "sbxd.sock")

	cmd := exec.Command("python3", append([]string{fakeSbxd, socket}, extraArgs...)...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { cmd.Process.Kill(); cmd.Wait() })
	if line, _ := bufio.NewReader(stdout).ReadString('\n'); line != "ready\n" {
		t.Fatalf("fake daemon did not start: %q", line)
	}
	return socket
}

func TestSmokeHealthAndList(t *testing.T) {
	ctx := context.Background()
	c, err := NewClient(ctx, startDaemon(t))
	if err != nil {
		t.Fatal(err)
	}

	health, err := c.Daemon.GetDaemonHealth(ctx)
	if err != nil || health.Status != "healthy" {
		t.Fatalf("health: %+v, %v", health, err)
	}
	sandboxes, err := c.Sandboxes.ListSandboxes(ctx)
	if err != nil || len(sandboxes) != 1 || sandboxes[0].Name != "claude-demo" {
		t.Fatalf("list: %+v, %v", sandboxes, err)
	}
}

func TestSmokeSocketFromEnvVar(t *testing.T) {
	ctx := context.Background()
	t.Setenv(SocketEnvVar, startDaemon(t))
	c, err := NewClient(ctx, "")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := c.Daemon.GetDaemonHealth(ctx); err != nil {
		t.Fatal(err)
	}
}

func TestSmokeToken(t *testing.T) {
	ctx := context.Background()
	socket := startDaemon(t, "--token", "s3cret")

	without, _ := NewClient(ctx, socket)
	if _, err := without.Sandboxes.ListSandboxes(ctx); err == nil {
		t.Fatal("expected a 401 without a token")
	}
	with, _ := NewClient(ctx, socket, option.WithToken("s3cret"))
	if _, err := with.Sandboxes.ListSandboxes(ctx); err != nil {
		t.Fatalf("with token: %v", err)
	}
}
