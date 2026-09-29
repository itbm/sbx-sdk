package sbx

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"time"
)

// SocketEnvVar names the environment variable that overrides socket discovery.
const SocketEnvVar = "SBX_SOCKET"

// DiscoveryTimeout bounds `sbx daemon status` when ctx has no deadline.
const DiscoveryTimeout = 10 * time.Second

var socketStatusPattern = regexp.MustCompile(`(?m)^Socket:\s*(\S+)`)

// DiscoverSocketPath parses the socket path out of `sbx daemon status`.
//
// The command prints the path whether or not the daemon is running, and may
// exit non-zero when it is stopped, so only the output is checked.
func DiscoverSocketPath(ctx context.Context) (string, error) {
	return discoverSocketPath(ctx, "sbx")
}

func discoverSocketPath(ctx context.Context, command string) (string, error) {
	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, DiscoveryTimeout)
		defer cancel()
	}

	var stdout, stderr bytes.Buffer
	cmd := exec.CommandContext(ctx, command, "daemon", "status")
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	// Don't wait on output pipes held open by a killed command's children.
	cmd.WaitDelay = time.Second
	runErr := cmd.Run()

	if ctxErr := ctx.Err(); ctxErr != nil {
		return "", fmt.Errorf("run `%s daemon status` to discover the socket path: %w", command, ctxErr)
	}
	if match := socketStatusPattern.FindSubmatch(stdout.Bytes()); match != nil {
		return string(match[1]), nil
	}

	var exitErr *exec.ExitError
	if runErr != nil && !errors.As(runErr, &exitErr) {
		return "", fmt.Errorf(
			"run `%s daemon status` to discover the socket path (is `%s` installed and on PATH?); set %s or pass socketPath explicitly instead: %w",
			command, command, SocketEnvVar, runErr)
	}
	return "", fmt.Errorf("could not parse a socket path from `%s daemon status` output (exit code %d):\n%s%s",
		command, cmd.ProcessState.ExitCode(), stdout.Bytes(), stderr.Bytes())
}

// ResolveSocketPath returns socketPath if non-empty, else $SBX_SOCKET if set,
// else the path discovered via DiscoverSocketPath.
func ResolveSocketPath(ctx context.Context, socketPath string) (string, error) {
	if socketPath != "" {
		return socketPath, nil
	}
	if fromEnv := os.Getenv(SocketEnvVar); fromEnv != "" {
		return fromEnv, nil
	}
	return DiscoverSocketPath(ctx)
}
