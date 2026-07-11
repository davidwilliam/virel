# Security policy

Security is a design tenet of Virel. The framework is meant to be safe
by default: an application written against the documented API
should not be expressible in a way that introduces the common web
vulnerability classes.

## Reporting a vulnerability

Email contact@davidwsilva.com with a description, reproduction steps, and
the affected version or commit. Please do not open a public issue for
anything you believe is exploitable. You can expect an acknowledgment
within a few days, and credit in the release notes once a fix ships unless
you prefer otherwise.

While the project is pre-release, fixes land on `main`; there are no
maintained release branches yet.

## What the framework guarantees

- All rendered text is HTML-escaped, in server-rendered output, in
  client-side bindings, and in list templates. Raw HTML requires an
  explicit `ui.unsafe_html(markup, reason=...)` call.
- Data embedded during server rendering is encoded so it cannot terminate
  or alter the surrounding inline script context.
- URLs flowing into `href`, `src`, and related attributes are scheme-checked
  at compile time for literals and at render time for dynamic values;
  `javascript:` and similar schemes are replaced with an inert fragment.
- HTML responses carry a content security policy that permits scripts only
  from the same origin plus the specific compiler-emitted inline scripts,
  matched by hash. Framing is denied and object embedding is disabled.
- Server actions validate every payload against the function signature and
  any declared model before user code runs, accept only JSON (never pickle
  or any object serialization), reject cross-site browser requests unless
  the origin is explicitly allowed, and cap request body size.
- Responses carry `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Cross-Origin-Opener-Policy`, and
  `Cross-Origin-Resource-Policy` headers by default.
- Static file serving resolves paths and refuses anything outside the
  public directory.

Escape hatches (`ui.unsafe_html`, raw JavaScript integrations) are explicit
and auditable; grepping for `unsafe` finds every use.

## Out of scope

Authentication, authorization, and session management are not yet part of
the framework; applications must enforce access control inside their server
actions. TLS termination, HSTS, and infrastructure hardening belong to the
deployment environment.
