# Handoff Log: AI Meeting Minutes Generator

- **Spec:** `specs/001-mvp-meeting-minutes-generator/spec.md`
- **Tasks:** `specs/001-mvp-meeting-minutes-generator/tasks.md`
- **Current Phase:** `In Progress (Claude Code)`
- **Engram Topic Key:** `spec/001-mvp-meeting-minutes-generator/decisions`

---

## 1. Handoff Status

- **Spec Status:** `Approved` (`Approved By: fede (Human)`, `2026-11-01`)
- **Last Updated By:** `Claude Code`
- **Completed Tasks:** `T1`
- **Pending Tasks:** `T2`, `T3`, `T4`, `T5`, `T6`, `T7`

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

| `2026-11-02` | `Claude Code` | RDD review `review-2fc0f8e5a799149e` (lenses risk + reliability) approved `3c0f410`; follow-up fix applies: class-based `CleanupStream` (async-generator `finally` never runs when `aclose()` precedes the first item), upload-dir hardening (refuse symlink / foreign owner, tighten mode to `0700` → `UnsafeUploadDirError` = HTTP 500), env-isolated settings tests, test tying `Settings.max_upload_bytes` to `MAX_UPLOAD_BYTES` Follow-up (2nd review `approved`): `CleanupStream.__del__` last-resort release + dangling-symlink upload dir → `UnsafeUploadDirError` | Closes an `S2` gap on early client disconnect and a shared-host tamper vector on the predictable default dir | — |

## 4. Open Questions & Blockers

- Specification and vertical slices (`T1`–`T7`) approved by human on `2026-11-01`.
- **Deferred RDD findings (contract changes → Ask First, non-blocking):**
  1. `S1` MP3 magic set is spec-exact (`ID3`/`FFFB`/`FFF3`/`FFF2`); valid untagged MPEG-1 L3 with CRC (`FFFA`) and MPEG-2.5 (`FFE3`/`FFE2`) are rejected with `415`. Widen the spec set?
  2. `TranscriptChunkPayload` (spec §5.1 verbatim) allows `end < start`. Add an `end >= start` validator?
- **Open hardening (3rd RDD review, approved, non-blocking):** guard `CleanupStream.__del__` against partially-initialised instances and exceptions; add tests for an abandoned `owned=False` stream (sample survives) and for a regular file at `upload_tmp_dir`. Fold into `T4` when the pipeline consumes `CleanupStream`.
- **`T4` note:** the SSE generator handed to `StreamingResponse` must wrap ASR/LLM with `stream_with_cleanup`/`temp_audio_file` **and consume it inside `async with aclosing(...)`** so a disconnect (before or after the first frame) unlinks the upload deterministically; `CleanupStream.__del__` is only a last-resort release for abandoned streams (GC timing is not deterministic while tracebacks hold frames); `UnsafeUploadDirError` maps to pre-stream `500 INTERNAL_ERROR`.

## 5. Next Action

- **Claude Code:** `T1` done. Next: `T2` (ASR strategies, `S3`/`S4`) and `T3` (LLM synthesizer, `S5`). Both reuse `app.config.Settings` and pinned deps without editing them. Gated decisions remain before `T4` (Contradiction #5, `S7` ASR DoS, sample asset) and `T5` (Contradiction #4).
