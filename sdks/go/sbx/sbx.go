// Package sbx is a hand-written convenience wrapper over the Fern-generated
// client.Client. It's a separate package (not the generated root package)
// because client.Client's dependencies import the root package, and
// importing client.Client from there would create an import cycle.
// Preserved across `make generate` via .fernignore.
package sbx

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os/exec"
	"regexp"

	client "github.com/itbm/sbx-sdk/sdks/go/client"
	option "github.com/itbm/sbx-sdk/sdks/go/option"
)

var socketStatusPattern = regexp.MustCompile(`(?m)^Socket:\s*(\S+)`)

// DiscoverSocketPath parses the socket path out of `sbx daemon status`,
// which prints it whether or not the daemon is running.
func DiscoverSocketPath(ctx context.Context) (string, error) {
	out, err := exec.CommandContext(ctx, "sbx", "daemon", "status").Output()
	if err != nil {
		return "", fmt.Errorf("run `sbx daemon status` to discover the socket path (is `sbx` installed and on PATH?): %w", err)
	}
	match := socketStatusPattern.FindSubmatch(out)
	if match == nil {
		return "", fmt.Errorf("could not parse a socket path from `sbx daemon status` output:\n%s", out)
	}
	return string(match[1]), nil
}

// NewClient constructs a client.Client wired to the local sbx daemon's unix
// socket. If socketPath is empty, it is discovered via DiscoverSocketPath.
// Extra opts are applied after the socket/base URL defaults, so callers can
// override them (e.g. option.WithToken).
//
// No token is set by default — sbx v0.34.0 doesn't enforce bearerAuth over
// the local socket. Pass option.WithToken(...) if a future version does.
func NewClient(ctx context.Context, socketPath string, opts ...option.RequestOption) (*client.Client, error) {
	if socketPath == "" {
		discovered, err := DiscoverSocketPath(ctx)
		if err != nil {
			return nil, err
		}
		socketPath = discovered
	}

	httpClient := &http.Client{
		Transport: &http.Transport{
			// host in the request URL is ignored; always dial the socket.
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				var d net.Dialer
				return d.DialContext(ctx, "unix", socketPath)
			},
		},
	}

	allOpts := append([]option.RequestOption{
		option.WithBaseURL("http://localhost"),
		option.WithHTTPClient(httpClient),
	}, opts...)

	return client.NewClient(allOpts...), nil
}
