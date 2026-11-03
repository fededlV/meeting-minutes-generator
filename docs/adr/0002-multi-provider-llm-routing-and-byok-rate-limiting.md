# ADR 0002: Multi-Provider OpenAI-Compatible LLM Routing and BYOK Rate Limiting

- **Status:** Accepted
- **Date:** 2026-10-31
- **Related Spec:** `specs/001-mvp-meeting-minutes-generator/spec.md`

## Context

Stage 2 of the pipeline synthesizes the timestamped meeting transcript into structured executive Markdown minutes (Executive Summary, Discussion Points, Takeaways, Action Items). Relying on a single paid LLM vendor creates a cost barrier and a single point of failure when free-tier quotas are exhausted by public visitors testing the portfolio app.

## Decision

1. **Unified OpenAI-Compatible Client (`AsyncOpenAI`):**
   - Standardize Stage 2 synthesis on the official `openai` Python SDK (`AsyncOpenAI`) calling `chat.completions.create(stream=True)` against provider-specific `base_url` endpoints:
     - **`huggingface`:** `https://router.huggingface.co/v1` (default model: `meta-llama/Llama-3.2-3B-Instruct`).
     - **`openrouter`:** `https://openrouter.ai/api/v1` (default model: `meta-llama/llama-3.2-3b-instruct:free`, fallback: `meta-llama/llama-3.3-70b-instruct:free`).
     - **`gemini`:** `https://generativelanguage.googleapis.com/v1beta/openai/` (default model: `gemini-2.5-flash`).
2. **Bring Your Own Key (BYOK) Precedence & IP Rate Limiting:**
   - Clients may pass `X-API-Key` or `X-HF-Token` (plus optional `X-LLM-Provider` and `X-LLM-Model`) in request headers.
   - When a valid non-empty BYOK header is present, the request uses that credential directly and **bypasses** the server fallback rate limiter.
   - When no BYOK header is present, the backend falls back to the environment-configured server credential (`LLM_API_KEY` / `HF_TOKEN` / `OPENROUTER_API_KEY` / `GEMINI_API_KEY`) and enforces an in-memory sliding-window rate limiter per client IP (default: `5` requests per `3600` seconds).
   - If neither a BYOK header nor a server key is configured, the pipeline emits a structured SSE `error` event (`code: "MISSING_API_KEY"`) instructing the user to open the BYOK configuration modal.

## Alternatives Considered

1. **`openai` (`AsyncOpenAI`) SDK with Provider Base URL Registry (Chosen):**
   - *Pros:* Lightweight dependency tree, full native async streaming (`AsyncStream[ChatCompletionChunk]`), native support across Hugging Face Inference Router, OpenRouter, and Google AI Studio OpenAI compatibility layer.
   - *Cons:* Requires maintaining a clean provider registry mapping (`provider -> (base_url, default_model, env_var)`).
2. **`litellm` Full SDK:**
   - *Rejected:* Pulls in heavy transitive dependencies and background telemetry/cost-map fetches that increase container startup time and image size unnecessarily when all three target providers already expose standard OpenAI `/v1/chat/completions` endpoints.
3. **Vendor-Specific SDKs (`google-genai`, `huggingface_hub` chat, etc.):**
   - *Rejected:* Multiplies code paths and mock targets for streaming token iteration.

## Consequences

- **Positive:** Single streaming code path (`AsyncOpenAI`) covers all three free-tier ecosystems; recruiters can test with server fallback keys up to the IP quota or bypass quotas instantly using their own key in the UI modal.
- **Negative / Risks:** User-supplied keys must never be logged or persisted server-side; the frontend stores BYOK tokens exclusively in `sessionStorage`/`localStorage` on the user's browser and sends them over HTTPS/local headers.
