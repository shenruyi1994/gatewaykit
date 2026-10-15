# GatewayKit Decisions

## Prioritization

I treated the non-negotiable requirements as a vertical slice before adding optional features. The implementation order was:

1. Start from YAML, expose the unconditional health endpoint, and prove it with a test.
2. Parse routes, match paths, filter methods, and proxy one GET request end to end.
3. Add POST bodies and headers, then explicit `502` behavior for unavailable upstreams.
4. Implement the products route's distinct behavior: prefix stripping, multiple targets, weighted round-robin balancing, timeout handling, and active health checks.
5. Add generic global defaults and route overrides for rate limits and timeouts.
6. Harden the gateway for alternate configurations, arbitrary method tokens, concurrent requests, and malformed known fields.

This order kept every stage runnable and testable. I chose a smaller set of complete capabilities over partially implementing every section in the example configuration.

## Architecture

The request pipeline is deliberately explicit:

```text
client request
  -> built-in /health check
  -> longest matching configured route
  -> configured method check
  -> effective rate limit (route override or global default)
  -> healthy upstream selection
  -> effective timeout (route override or global default)
  -> standard-library HTTP client
  -> filtered upstream response
```

Responsibilities are separated by module:

- `config.py` parses and validates known YAML fields into immutable configuration objects.
- `router.py` performs segment-aware, longest-prefix route selection.
- `rate_limiter.py` owns fixed-window and sliding-window state.
- `health.py` probes configured targets and tracks consecutive failures and recovery.
- `load_balancer.py` owns round-robin selection state.
- `proxy.py` constructs the upstream request and translates transport failures.
- `server.py` composes those pieces into the HTTP pipeline.

This keeps policy state out of the request handler and makes another configuration feature addable without replacing the proxy core.

## Behavioral decisions and trade-offs

### Standard library instead of a proxy framework

The implementation uses `ThreadingHTTPServer`, `HTTPConnection`, and `HTTPSConnection`. PyYAML is used only for configuration parsing. Routing, forwarding, load balancing, rate limiting, health tracking, and error mapping are implemented in this repository.

### Route matching

A route matches its exact path or a child path on a segment boundary, so `/api/users` does not match `/api/users-old`. If several routes match, the most specific path wins.

### Configuration compatibility

Known fields fail fast with location-specific `ConfigError` messages. Unknown sections are ignored so the full supplied schema—and future extensions—can still load even when an optional behavior is not implemented. Custom valid HTTP method tokens such as `PURGE` are accepted and proxied when configured.

I kept the complete supplied example in `gateway.yaml` rather than deleting
unsupported sections. Loading the full file demonstrates forward-compatible
parsing, but does not imply that every policy is active. Unsupported policies
are called out explicitly in the README and below; silently approximating them
would be less predictable than leaving them disabled.

### Rate limiting

The global policy is a default applied independently to routes that do not override it. Buckets are route-scoped: `per: ip` separates direct client IPs, while `per: global` shares a route's bucket across clients. Rejected requests receive `429` and `Retry-After`.

State is protected by a lock, and an integration test releases 50 requests simultaneously to verify the configured number succeeds atomically. State is intentionally in memory, so it is neither persistent nor shared across processes.

### Concurrency

The server uses one standard-library request thread per connection. Rate-limit, health, and load-balancer state is synchronized. Request threads are daemons so shutdown is not held open by stalled clients. This is a pragmatic take-home choice rather than a claim that `http.server` is production infrastructure.

### Upstream failures and health

Connection failures become `502`; configured timeouts become `504`. Health checks treat `2xx` and `3xx` responses as successful. Targets begin eligible, become unhealthy after the configured number of consecutive failures, and rejoin after a successful probe. If every target is unhealthy, the gateway returns `503` rather than selecting a known-bad target.

### Header and body handling

Hop-by-hop headers and the inbound `Host` and `Content-Length` are not forwarded. The HTTP client recalculates framing for buffered bodies. Streaming and chunked request bodies are out of scope; requests with bodies must provide `Content-Length`.

The direct socket address is used for per-IP limits. Trusting `X-Forwarded-For` without a configured trusted-proxy boundary would allow clients to choose their own bucket.

## Incomplete features

The following sections are present in the supplied `gateway.yaml` but are ignored by the current parser:

- `retry`: no fixed or exponential retry loop
- `request_transform` and `response_transform`: no header or JSON body transformation
- `auth`: no API-key enforcement
- `circuit_breaker`: no rolling failure window or cooldown state

These routes still receive common routing and proxy behavior. There are no half-enabled versions of the omitted policies.

## What I would build next

1. Retry policy with bounded attempts, retryable status codes, backoff, and idempotency safeguards.
2. API-key authentication, followed by circuit-breaking state and half-open recovery.
3. A typed transformation pipeline for request and response headers and JSON bodies.
4. Streaming/chunked request and response support, connection pooling, structured logs, and metrics.
5. Rate-limit bucket eviction or bounded caches, graceful draining, and shared state for multi-process deployment.

## Use of AI tools

I used an AI coding assistant as an iterative pair programmer: to compare implementation choices against the requirements, draft small changes and tests, identify failure modes, and review the evolving architecture. I remained responsible for scope and technical decisions rather than treating generated suggestions as authoritative. I kept the work incremental, verified each behavior with tests, and maintained a commit history that reflects the order in which the gateway was built.

### Human review and corrections

My review changed the proposed design in several concrete ways:

- I rejected starting with a broad implementation and instead established the unconditional `/health` endpoint first, followed by one end-to-end users route. This produced a working vertical slice before optional behavior was added.
- I clarified that rate limiting is defined as a global default with per-route overrides. The implementation therefore resolves an effective policy for every route instead of treating rate limiting as a feature belonging only to one example endpoint.
- I rejected a hardcoded HTTP-method allowlist. A supplied configuration may contain a valid method that is absent from the example, so configured method tokens are validated syntactically and forwarded generically. The acceptance test uses `PURGE` to prove this behavior.
- I redirected the next multi-upstream implementation from an invented orders flow to the supplied products route, keeping development grounded in the provided schema.
- I prioritized a basic successful proxy request before adding timeout and resilience behavior, making the request path testable before introducing more failure states.
- I required mock upstreams to be part of the test suite, so proxy, timeout, health-check, and concurrency behavior can be exercised without external services.
- I questioned whether `ThreadingHTTPServer` complied with the no-proxy-framework constraint before adopting it. It is a permitted standard-library HTTP server; the gateway's routing and proxy policies remain implemented here.
- I used the requirement that the gateway work with a different valid configuration to challenge example-specific assumptions. This led to alternate-config acceptance coverage, generic route and method handling, validation of known fields, and tolerance of unknown optional sections.

These corrections are part of the engineering process represented by the submission: AI accelerated drafting and review, while I set priorities, challenged assumptions, redirected implementation, and accepted changes only after understanding their behavior. I am prepared to explain the resulting code and trade-offs in the walkthrough.
