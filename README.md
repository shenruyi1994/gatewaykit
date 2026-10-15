# GatewayKit

GatewayKit is a lightweight, configuration-driven API gateway built with Python's standard-library HTTP server and client. It implements the proxy behavior directly; PyYAML is the only third-party runtime dependency.

## Prerequisites

- Python 3.9 or newer
- `pip`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For the shortest reviewer path, the same setup and test run are available as:

```bash
make setup
make test
```

## Run the gateway

Pass the YAML configuration path as the command-line argument:

```bash
python -m gatewaykit gateway.yaml
```

The supplied configuration listens on port 8080. The administrative health endpoint does not depend on an upstream:

```bash
curl -i http://localhost:8080/health
```

Expected body:

```json
{"status":"healthy","uptime_seconds":0}
```

To try basic proxying, start the included mock users upstream in another terminal:

```bash
source .venv/bin/activate
python -m tests.mock_upstream
```

The default port is `3001`. Use `--port` to exercise another configured
upstream, for example `python -m tests.mock_upstream --port 3002`.

Then call the configured users route:

```bash
curl -i 'http://localhost:8080/api/users/123?details=true'
```

## Run the tests

The test suite is self-contained and starts mock upstreams on temporary local ports:

```bash
source .venv/bin/activate
python -m unittest discover -v
```

Alternatively, run `make test`. No separately running gateway or upstream is
required for either command.

## Example route support

All five configured routes receive the implemented common pipeline: routing,
method filtering, proxying, applicable prefix stripping, timeouts, and effective
global or route-level rate limits. Route-specific support is:

| Route | Implemented from the supplied configuration | Intentionally omitted |
| --- | --- | --- |
| `/api/users` | Proxying, methods, bodies and headers, route rate limit | None |
| `/api/orders` | Proxying, methods, route timeout, route rate limit | Retry and backoff |
| `/api/products` | Prefix stripping, weighted round robin, timeout, active health checks | None |
| `/api/legacy` | Proxying, methods, prefix stripping, global defaults | Request and response transformations |
| `/api/internal` | Proxying, methods, global defaults | API-key authentication and circuit breaking |

The standalone mock command starts one upstream at a time and defaults to the
users service's port `3001`. Other example routes require mock processes on
their configured ports. The automated suite instead creates every upstream it
needs on temporary ports.

## Implemented capabilities

- Config-driven port, routes, prefix stripping, and arbitrary valid HTTP methods
- Segment-aware longest-route matching with `404`, `405`, and `Allow`
- HTTP/HTTPS forwarding of methods, paths, queries, headers, and buffered bodies
- Single-target, round-robin, and weighted round-robin upstream selection
- Global timeout and rate-limit defaults with route overrides
- Fixed/sliding windows, per-IP/route-global buckets, `429`, and `Retry-After`
- Active health checks plus explicit `502`, `503`, and `504` failure behavior
- Concurrent handling with synchronized shared state and validated known config fields

## Not implemented

The complete supplied YAML remains in `gateway.yaml`, but these optional behaviors are intentionally left for future work:

- [ ] Retry policies and backoff
- [ ] Request and response transformations
- [ ] API-key authentication
- [ ] Circuit breaking

Routes containing these sections still receive the implemented common behavior,
but the unimplemented sections are ignored rather than partially enforced. In
particular, `/api/internal` does not enforce its configured API keys.

## Current limitations

- Runtime state is in memory and local to one gateway process.
- Request bodies require `Content-Length`; streaming and chunked request bodies are not implemented.
- Client identity uses the direct socket IP and does not trust `X-Forwarded-For`.
- Configuration is loaded once at startup; live reload is not implemented.
- The standard-library server is appropriate for this exercise, not a hardened internet-facing deployment.

See [DECISIONS.md](DECISIONS.md) for architecture, prioritization, and trade-offs.
