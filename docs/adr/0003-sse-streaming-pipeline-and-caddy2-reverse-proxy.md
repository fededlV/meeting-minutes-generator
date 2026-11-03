# ADR 0003: Real-Time SSE Streaming Pipeline, Next.js App Router, and Caddy 2 Gateway

- **Status:** Accepted
- **Date:** 2026-10-31
- **Related Spec:** `specs/001-mvp-meeting-minutes-generator/spec.md`

## Context

Transcribing several minutes of meeting audio and generating comprehensive Markdown minutes takes $10\text{–}90\text{ seconds}$ on CPU/free APIs. A traditional synchronous REST `POST` response leaves the user staring at a spinner and risks proxy timeouts (`504 Gateway Timeout`). Furthermore, reverse proxies buffer upstream HTTP responses by default, which breaks incremental token and segment delivery unless explicitly configured.

## Decision

1. **Single-Request Multipart SSE Pipeline (`POST /api/minutes/generate`):**
   - Accepts `multipart/form-data` (`file` upload or `use_sample=true` form field) and returns `text/event-stream` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`).
   - Streams four typed SSE event kinds (`status`, `transcript_chunk`, `llm_token`, `error`) using Python async generators (`yield`) and guarantees temporary file deletion inside the generator's `finally:` block.
2. **Next.js (App Router) Standalone Frontend:**
   - Uses Next.js App Router (`output: 'standalone'`) with TypeScript, Tailwind CSS, `lucide-react`, and `react-markdown` + `remark-gfm`.
   - Consumes the multipart POST SSE response via browser `fetch()` + `ReadableStream` (`TextDecoder` line-buffered SSE parser) because native `EventSource` only supports `GET` without custom headers or `FormData` bodies.
3. **Caddy 2 Reverse Proxy (`caddy:2-alpine`):**
   - Acts as the sole public ingress (`:8080` / `:80`), routing `/api/*` to `backend:8000` and `/*` to `frontend:3000` over an isolated Docker bridge network.
   - Enforces `request_body { max_size 30MB }` to permit up to $25\text{ MB}$ multipart audio uploads without `413 Payload Too Large` errors.
   - Configures `reverse_proxy backend:8000` with `flush_interval -1` (zero proxy buffering for immediate SSE flushing) and `transport http { read_timeout 300s }`.
   - Runs all containers (`backend`, `frontend`, `caddy`) as non-root UIDs.

## Alternatives Considered

1. **Multipart `POST` returning `text/event-stream` via `fetch` `ReadableStream` behind Caddy 2 (Chosen):**
   - *Pros:* Stateless single request—no server-side job store, Redis queue, or sticky session required to link a preliminary upload ID to a subsequent `GET` stream; temporary audio file lives only for the lifetime of the active generator.
   - *Cons:* Requires a small, deterministic SSE frame parser (`event:` / `data:` splitter) over `response.body.getReader()` on the frontend.
2. **Two-Step Upload (`POST /upload` -> `GET /stream/:jobId` with `EventSource`):**
   - *Rejected:* Requires storing uploaded audio files across requests on disk/Redis, introduces orphan file cleanup timers if the client never connects to `GET /stream/:jobId`, and cannot pass `X-API-Key` headers via standard browser `EventSource`.
3. **WebSockets:**
   - *Rejected:* Bidirectional sockets are unnecessary for a unidirectional upload-then-stream workflow and add proxy/reconnection complexity.

## Consequences

- **Positive:** Zero-state backend architecture; immediate visual feedback via the 4-stage stepper, live clickable transcript timestamps, and token-by-token Markdown rendering; zero proxy buffering through Caddy 2's `flush_interval -1`.
- **Negative / Risks:** The SSE parser in `useMinutesStream.ts` must properly handle chunk boundaries (where a single network read contains partial or multiple `\n\n`-delimited SSE frames).
