# Handoff Log: AI Meeting Minutes Generator

- **Spec:** `specs/001-mvp-meeting-minutes-generator/spec.md`
- **Tasks:** `specs/001-mvp-meeting-minutes-generator/tasks.md`
- **Current Phase:** `In Progress (Claude Code)`
- **Engram Topic Key:** `spec/001-mvp-meeting-minutes-generator/decisions`

---

## 1. Handoff Status

- **Spec Status:** `Approved` (`Approved By: fede (Human)`, `2026-11-01`)
- **Last Updated By:** `Claude Code`
- **Completed Tasks:** `T1`, `T2`
- **Pending Tasks:** `T3`, `T4`, `T5`, `T6`, `T7`

## 2. Spec-Challenge Notes (Filled by Claude Code in Plan Mode Before Coding)

- **Entry Gate:** PASSED — `spec.md` declares `Status: Approved` (`Approved By: fede (Human)`, `Approval Date: 2026-11-01`); Open Questions: none. Reviewed `2026-11-02`.

### Contradictions Found
1. `ASRStrategy` Protocol is declared `async def transcribe(...) -> AsyncIterator[...]`; an async-generator implementation does not match that signature under mypy (coroutine-returning-iterator vs. async generator). Implement the Protocol as `def transcribe(self, audio_path: Path) -> AsyncIterator[TranscriptChunkPayload]`. GLOSSARY uses `file_path`; spec uses `audio_path` → use `audio_path`.
2. GLOSSARY `ApiWhisperASR` says `InferenceClient`; `S4` / ADR-0001 say `AsyncInferenceClient` → use the async client.
3. AGENTS.md lists `services/llm/client.py`; spec tree and `T3` use `synthesizer.py` → follow the spec.
4. Testing Strategy covers `S9`–`S11` only via tsc/lint/build, while the AGENTS.md DoD requires every `S#` verified by automated tests. `npm test -- --run` also implies Vitest, which is not in the Section 3 stack. → **Decision required before `T5`** (add Vitest + Testing Library + jsdom vs. manual checklist for `S9`–`S11`).
5. §5.3 lists pre-stream `422`, but `ErrorCode` has no request-validation code (missing `file` with `use_sample=false`, both `file` + `use_sample=true`, invalid `X-LLM-Provider` / `X-ASR-Mode`). → **Decision required before `T4`** (proposed: add `INVALID_REQUEST`; public contract change → Ask First).
6. `T2` and `T3` are routed as parallel sub-agents but both would need to edit `config.py` and `requirements.txt` → `T1` defines ALL settings and pins ALL backend deps upfront so `T2`/`T3` edit surfaces stay disjoint.

### Missing Edge Cases / Failure Modes
- **`S1`:** M4A `ftyp` sits at offset 4 and WAV `WAVE` at offset 8 (not "leading"); magic bytes must match the extension's family (`.mp3` carrying WAV bytes → `415`). Size cap enforced while streaming to disk (chunked read, abort at `26,214,401` bytes), never buffering 25 MB in RAM. Check order: rate limit (`429`) → size (`413`) → extension/MIME/magic (`415`).
- **`S1`/`S2`:** "restricted temp directory" ≠ shared `tempfile.gettempdir()`; use an injectable `UPLOAD_TMP_DIR` (default `gettempdir()/mmg-uploads`, mode `0700`) so "zero orphan files" is testable against `tmp_path`.
- **`S2`/`S8`:** cleanup must be ownership-aware — only unlink files the request created, never the bundled sample. Cancellation does not stop the ASR worker thread; add a stop flag checked between segments so CPU work ends on client disconnect.
- **`S3`:** lazy singleton must be thread-safe (lock); `faster-whisper` imported lazily so tests patch it without loading CTranslate2. Model size validated against `{base.en, small.en}`. Non-root UID 1001 needs a writable `HF_HOME` (`T7`).
- **`S4`:** `AsyncInferenceClient` uses aiohttp → `respx` cannot intercept it; mock the client with `unittest.mock`. Missing timestamps → single segment `[0.0, duration]` (ADR-0001). MVP implements the Hugging Face path only (the OpenAI-compatible ASR endpoint is an "or").
- **`S5`:** fence stripping must work across arbitrary token splits (e.g. ` `` ` + `` `markdown\n ``) → buffered stripper tested at every split point. Zero tokens from the LLM → `LLM_QUOTA_OR_UPSTREAM_ERROR`. Very long transcripts vs. context window → configurable `MAX_TRANSCRIPT_CHARS` truncation with a notice. Provider base URLs and default models taken from ADR-0002.
- **`S6`:** `error` is terminal (no `completed` after it) and may follow partial `llm_token` frames. Silence (zero segments) → `ASR_FAILURE` and the LLM is skipped. `MISSING_API_KEY` is emitted after transcript chunks, in place of `analyzing`. SSE comment heartbeat (`: ping`) during long CPU transcription; the frontend parser must ignore comment lines.
- **`S7` (security):** any non-empty `X-API-Key` bypasses the limiter, so a garbage key buys unlimited local CPU ASR (DoS vector). → **Decision required before `T4`** (proposed: global local-ASR concurrency semaphore independent of BYOK). Credential routing: LLM uses `X-API-Key` (fallback `X-HF-Token` for `huggingface`); API ASR uses `X-HF-Token` → `X-API-Key` → `HF_TOKEN`. `X-Forwarded-For` trusted only from the Caddy peer (uvicorn `--proxy-headers --forwarded-allow-ips`). In-memory limiter assumes a single uvicorn worker. Rejected (`413`/`415`) requests do not consume quota.
- **`S8`:** bundled `denver_council_sample.mp3` must be supplied (source + license) → **Human input required before `T4`**. Tests use generated fixture bytes, never the real asset. `use_sample=true` with a missing asset → pre-stream `500` `INTERNAL_ERROR`.
- **`S9`/`S11`:** timestamps ≥ 60 min render with `MM` overflow (e.g. `75:30`) — accepted. BYOK token stored in `sessionStorage` (provider/model in `localStorage`) to limit XSS exposure. Download filename `meeting-minutes-YYYY-MM-DD.md`. Object URLs revoked on file change. Dev-mode API routing via `next.config` rewrites to `backend:8000`.
- **`S12`:** `caddy:2-alpine` has no non-root user — create UID 1001 with writable `/data` and `/config`. Add a compose `mem_limit` so the `< 1.5 GB` objective is enforceable.

### Untestable Criteria
- **`S5`** "yields tokens containing the 4 headings" depends on a real LLM → test that the system prompt mandates the exact headings and that a fake stream passes through intact.
- **`S3`** "without blocking the asyncio loop" → test via a concurrent ticker task that keeps advancing while the fake segment iterator blocks synchronously.
- **`S1`** HTTP status codes and **`S2`** pipeline-level cleanup are only observable once the endpoint exists → `T1` verifies at validator/cleanup unit level; `T4` re-verifies end-to-end.
- **`< 1.5 GB` RAM** (Objective) has no `S#` or test → covered by compose `mem_limit` plus a manual smoke check in `T7`.

### T2 Spec-Challenge Notes (`2026-11-03`, non-blocking)
1. `TranscriptChunkPayload` still lacks the `end >= start` validator decided for `T4`; `T2` normalizers (`asr.base.to_chunk`) already clamp `end = max(end, start)`, so adding the validator in `T4` is safe.
2. ADR-0001 says API fallback segment `[0.0, duration]`; task brief says `[0.0, 0.0]` → `[0.0, 0.0]` used (duration is unknown without decoding audio locally, which `S4` forbids).
3. No `Settings` field for the remote ASR model id; adding an env var is "Ask First" → module constant `DEFAULT_API_ASR_MODEL = "openai/whisper-large-v3"`, overridable via constructor.
4. API token precedence: BYOK `api_key` (router resolves `X-HF-Token`/`X-API-Key` in `T4`) → `HF_TOKEN` → `LLM_API_KEY` (last fallback added per task brief; `S4` lists only the first three).
5. `S3` non-blocking is verified by asserting the decoder runs on a non-loop thread plus a decoder that blocks until the consumer has received chunk 1 (instead of the ticker idea above).

### Environment Note
- Local dev venv uses Python 3.14 (human decision `2026-11-02`): `uv venv --python 3.14 --seed backend/.venv`, then the AGENTS.md pip install. Spec §3 / `S12` still pin the container to `python:3.12-slim`; local 3.14 vs. container 3.12 drift is accepted (code stays 3.12-compatible, e.g. ruff `target-version = "py312"`). Risk: `ctranslate2` / `faster-whisper` cp314 wheels — verified at install in `T1`; if missing, stop and ask.
- Work happens directly on `main` (human decision `2026-11-02`, supersedes the earlier feature-branch note); Conventional Commits without AI attribution.
- `ctranslate2==4.8.5` / `faster-whisper==1.2.1` cp314 wheels installed cleanly (risk closed). All backend deps pinned with `==` in `T1`.

- **Resolution:** `Cleared to build` — no blocker for `T1`. Gated decisions: Contradiction #5, `S7` ASR DoS mitigation, and the sample asset before `T4`; Contradiction #4 before `T5`.

## 3. Durable Decisions & Rationale

| Date | Actor | Decision | Rationale / Tradeoff | Engram / ADR Ref |
|---|---|---|---|---|
| `2026-10-31` | `Human + Antigravity` | Use **Caddy 2** (`caddy:2-alpine`) as the sole reverse proxy instead of NGINX | Eliminates mixed NGINX/Caddy config drift; uses native `flush_interval -1`, `request_body { max_size 30MB }`, and `read_timeout 300s` for zero-buffer SSE streaming | [ADR-0003](file:///home/fede/Proyectos/meeting-minutes-generator/docs/adr/0003-sse-streaming-pipeline-and-caddy2-reverse-proxy.md) |
| `2026-10-31` | `Human + Antigravity` | Use **Next.js (App Router)** with TypeScript, Tailwind CSS, and `output: 'standalone'` | Matches target fullstack portfolio stack while keeping production container lightweight on `node:22-alpine` (`UID 1001`) | [ADR-0003](file:///home/fede/Proyectos/meeting-minutes-generator/docs/adr/0003-sse-streaming-pipeline-and-caddy2-reverse-proxy.md) |
| `2026-10-31` | `Human + Antigravity` | Dual-mode ASR Strategy (`local` via `faster-whisper` CPU `int8` + `vad_filter=True` default; `api` via HF/OpenAI audio endpoint) | Keeps container RAM `< 1.5 GB` without CUDA and allows Instant Demo Mode transcription to work offline out-of-the-box | [ADR-0001](file:///home/fede/Proyectos/meeting-minutes-generator/docs/adr/0001-dual-mode-asr-strategy-and-cpu-int8-optimization.md) |
| `2026-10-31` | `Human + Antigravity` | Standardize LLM synthesis on `AsyncOpenAI` across Hugging Face, OpenRouter (`:free`), and Google Gemini (`gemini-2.5-flash`) with BYOK header override and IP rate limiting | Single streaming code path across 3 free-tier providers; recruiters can use server fallback within IP quota or bypass via BYOK modal | [ADR-0002](file:///home/fede/Proyectos/meeting-minutes-generator/docs/adr/0002-multi-provider-llm-routing-and-byok-rate-limiting.md) |
| `2026-11-02` | `Claude Code` | **T1 validation order:** extension + Content-Type (no disk I/O) → chunked stream with size cap (`413` at `26,214,401` bytes) → magic bytes checked as soon as 12 bytes are buffered (`415`). Refines the earlier "size → format" note | Never writes untrusted bytes to disk when the name/MIME already disqualify the upload; fails fast on wrong magic without reading 25 MB. Consequence: a 30 MB `.exe` returns `415`, not `413` | Engram `spec/001-mvp-meeting-minutes-generator/decisions` |
| `2026-11-02` | `Claude Code` | **Upload dir & cleanup ownership:** `Settings.upload_tmp_dir` (default `gettempdir()/mmg-uploads`, created `0700`); `temp_audio_file(path, owned=)` / `stream_with_cleanup(...)` unlink only `owned=True` files, synchronously inside `finally` | Injectable dir makes "zero orphan files" testable; sync `unlink` cannot be interrupted by a second cancellation; `owned=False` protects the bundled sample (`S8`). File writes/`mkdir` go through `asyncio.to_thread` | Engram `spec/001-mvp-meeting-minutes-generator/decisions` |
| `2026-11-02` | `Claude Code` | Secrets (`BYOKHeaders.x_api_key/x_hf_token`, `Settings.*_api_key/hf_token`) typed as `SecretStr` | Tokens never appear in `repr`/logs (AGENTS.md "Never log BYOK tokens") | — |
| `2026-11-02` | `Human + Antigravity` | **T4 Decisions Resolved:** (1) Widened MP3 signatures to include `0xFFFA` and `0xFFE3`/`0xFFE2`; (2) Enforced `end >= start` in `TranscriptChunkPayload`; (3) Added `ErrorCode.INVALID_REQUEST` for 422 pre-stream validation; (4) Sample audio provided in `backend/assets/denver_council_sample.mp3` from MeetingBank (CC BY 4.0 / Public records); (5) Mitigated `S7` ASR DoS via global local-ASR semaphore (`asyncio.Semaphore(1)`) + local CPU ASR always subject to per-IP quota regardless of LLM BYOK key | Protects cloud server CPU from exhaustion while preserving multi-provider free LLM options (Hugging Face, OpenRouter, Google AI Studio); keeps demo and testing zero-cost | [spec.md](file:///home/fede/Proyectos/meeting-minutes-generator/specs/001-mvp-meeting-minutes-generator/spec.md) |
| `2026-11-02` | `Human` | **S7 busy-CPU response:** when the local ASR semaphore is held, reject pre-stream with HTTP `503` (non-blocking acquire), not `429` | Server saturation is not a client quota violation; a distinct status lets the UI suggest switching to Remote API mode. Semaphore and `413`/`415` rejections do not consume per-IP quota. **Pending spec amendment:** `S7` text still says "`429` (or `503`)"; proposed additions `ErrorCode.SERVER_BUSY` + `Retry-After` header need confirmation | — |
| `2026-11-03` | `Claude Code` | **T2 ASR engine:** `ASRStrategy.transcribe` declared as `def ... -> AsyncIterator` (async-generator compatible; spec's `async def` form would type as a coroutine); `faster_whisper` imported lazily inside `get_whisper_model` and strategies imported lazily in `factory`, so `api` mode never loads CTranslate2; model cached per size behind a `threading.Lock`; decoder runs in `asyncio.to_thread` feeding an `asyncio.Queue` via `call_soon_threadsafe`, with a `threading.Event` stop flag set in the consumer's `finally` (cancel/`aclose()` stops decoding after the current segment); missing API token raises `ASRError(MISSING_API_KEY)` at construction (pre-stream); upstream API errors re-raised with a fixed message (no credential echo) | Keeps loop responsive and RAM bounded; fail-fast token check lets `T4` reject before opening the SSE stream | Engram `spec/001-mvp-meeting-minutes-generator/decisions` |

## 4. Open Questions & Blockers

- Specification and vertical slices (`T1`–`T7`) approved by human on `2026-11-01`.
- **Decisions Cleared for T4:**
  - `S1` MP3 magic signatures widened.
  - `TranscriptChunkPayload` `end >= start` validated.
  - `ErrorCode.INVALID_REQUEST` added.
  - `S7` Local CPU ASR rate-limit DoS vector closed (global semaphore `Semaphore(1)` + IP quota strictly applies to local CPU compute).
  - `S8` Sample audio asset supplied and documented in `backend/assets/`.
- **Pending spec amendment before T4:** `S7` must state `503` (decided `2026-11-02`); confirm `SERVER_BUSY` error code + `Retry-After`.
- **Remaining for T5:** Contradiction #4 (Frontend testing strategy).
- **Open hardening for T4:** Guard `CleanupStream.__del__` against partially-initialised instances; test abandoned `owned=False` stream; test regular file at `upload_tmp_dir`.

- **Open hardening from T2 RDD review (`review-26a7c9c0776f2697`, approved, advisories only):**
  - `api_whisper`: response parsing (empty/`None` timestamps, `None` text) and `read_bytes` `OSError` escape as raw exceptions → wrap into `ASRError` like the local strategy.
  - `api_whisper`: `raise ASRError(...) from exc` keeps a possibly token-bearing `__cause__`; `T4` must not log the cause chain (or use `from None`).
  - `factory`: whitespace-only BYOK key stops the fallback chain → treat blank as missing.
  - `factory`: `LLM_API_KEY` fallback may send an OpenRouter/Gemini key to Hugging Face → **human decision needed** (keep, restrict to `huggingface` provider, or drop).

## 5. Next Action

- **Claude Code:** `T2` done. Proceed with `T3` (LLM synthesizer, `S5`); `T4` consumes `get_asr_strategy` and must map `ASRError.code` to `event: error`. Gated decisions for `T4` are all resolved and cleared.
