// Package sbx is a hand-written convenience wrapper over the Fern-generated
// client.Client. It's a separate package (not the generated root package)
// because client.Client's dependencies import the root package, and
// importing client.Client from there would create an import cycle.
// Preserved across `make generate` via .fernignore.
package sbx

import (
	"context"
	"net"
	"net/http"
	"time"

	client "github.com/itbm/sbx-sdk/sdks/go/client"
	option "github.com/itbm/sbx-sdk/sdks/go/option"
)

// NewClient constructs a client.Client wired to the local sbx daemon's unix
// socket. The socket is resolved by ResolveSocketPath: socketPath if
// non-empty, else $SBX_SOCKET, else `sbx daemon status`.
// Extra opts are applied after the socket/base URL defaults, so callers can
// override them (e.g. option.WithToken).
//
// No token is set by default — sbx v0.34.0 doesn't enforce bearerAuth over
// the local socket. Pass option.WithToken(...) if a future version does.
func NewClient(ctx context.Context, socketPath string, opts ...option.RequestOption) (*client.Client, error) {
	socketPath, err := ResolveSocketPath(ctx, socketPath)
	if err != nil {
		return nil, err
	}

	allOpts := append([]option.RequestOption{
		option.WithBaseURL("http://localhost"),
		option.WithHTTPClient(NewHTTPClient(socketPath)),
	}, opts...)

	return client.NewClient(allOpts...), nil
}

// NewHTTPClient returns an *http.Client that sends every request to the unix
// socket at socketPath, whatever host the request URL names. Use it with
// option.WithHTTPClient to customise the client further.
func NewHTTPClient(socketPath string) *http.Client {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	return &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return dialer.DialContext(ctx, "unix", socketPath)
			},
			MaxIdleConns:    10,
			IdleConnTimeout: 90 * time.Second,
		},
	}
}
