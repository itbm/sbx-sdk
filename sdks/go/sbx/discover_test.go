package sbx

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var fakeSbx, _ = filepath.Abs("../../../tests/fixtures/fake-sbx")

func TestDiscoverParsesSocketLine(t *testing.T) {
	t.Setenv("FAKE_SBX_SOCKET", "/run/sbx/sandboxd.sock")
	got, err := discoverSocketPath(context.Background(), fakeSbx)
	if err != nil || got != "/run/sbx/sandboxd.sock" {
		t.Fatalf("got %q, %v", got, err)
	}
}

func TestDiscoverToleratesNonZeroExit(t *testing.T) {
	// A stopped daemon still prints the socket path.
	t.Setenv("FAKE_SBX_SOCKET", "/run/sbx/sandboxd.sock")
	t.Setenv("FAKE_SBX_EXIT", "1")
	got, err := discoverSocketPath(context.Background(), fakeSbx)
	if err != nil || got != "/run/sbx/sandboxd.sock" {
		t.Fatalf("got %q, %v", got, err)
	}
}

func TestDiscoverFailsWithoutSocketLine(t *testing.T) {
	t.Setenv("FAKE_SBX_NO_SOCKET", "1")
	_, err := discoverSocketPath(context.Background(), fakeSbx)
	if err == nil || !strings.Contains(err.Error(), "could not parse a socket path") {
		t.Fatalf("got %v", err)
	}
}

func TestDiscoverFailsWhenCommandMissing(t *testing.T) {
	_, err := discoverSocketPath(context.Background(), "/nonexistent/sbx")
	if err == nil || !strings.Contains(err.Error(), "is `/nonexistent/sbx` installed") {
		t.Fatalf("got %v", err)
	}
}

func TestDiscoverRespectsContextDeadline(t *testing.T) {
	slow := filepath.Join(t.TempDir(), "slow-sbx")
	if err := os.WriteFile(slow, []byte("#!/bin/sh\nsleep 5\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	start := time.Now()
	_, err := discoverSocketPath(ctx, slow)
	if err == nil || time.Since(start) > 3*time.Second {
		t.Fatalf("got %v after %s", err, time.Since(start))
	}
}

func TestResolveOrder(t *testing.T) {
	t.Setenv(SocketEnvVar, "/from/env.sock")
	if got, _ := ResolveSocketPath(context.Background(), "/explicit.sock"); got != "/explicit.sock" {
		t.Fatalf("explicit: got %q", got)
	}
	if got, _ := ResolveSocketPath(context.Background(), ""); got != "/from/env.sock" {
		t.Fatalf("env: got %q", got)
	}

	// With no env var, fall back to `sbx` on PATH.
	t.Setenv(SocketEnvVar, "")
	bin := t.TempDir()
	if err := os.Symlink(fakeSbx, filepath.Join(bin, "sbx")); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("FAKE_SBX_SOCKET", "/from/cli.sock")
	if got, err := ResolveSocketPath(context.Background(), ""); got != "/from/cli.sock" {
		t.Fatalf("cli: got %q, %v", got, err)
	}
}
