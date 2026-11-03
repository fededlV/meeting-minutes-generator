# Implementation Tasks: AI Meeting Minutes Generator

- **Spec Reference:** `specs/001-mvp-meeting-minutes-generator/spec.md` (`Status` must be `Approved` before execution)
- **Delivery Strategy:** Vertical slices (`<= 400` changed lines per commit), TDD (`Red -> Green -> Refactor`), dependency-ordered.

---

## Dependency Graph

```text
T1 (Core Schemas, Config, Audio Validator & Temp Cleanup)
 ├──► T2 (Dual-Mode ASR Strategy Engine: Local CPU INT8 & API Mode)
 ├──► T3 (Multi-Provider LLM Synthesizer & Executive Minutes Prompts)
 │     │
 └─────┴──► T4 (FastAPI SSE Pipeline, BYOK Rate Limiter, Sample Asset & Integration Tests)
             │
             ├──► T5 (Next.js App Router Foundation, SSE Parser Hook & Upload/Audio Player UI)
             │     │
             │     └──► T6 (Split-View Transcript/Minutes UI, Stepper, BYOK Modal & MD/PDF Export)
             │           │
             └───────────┴──► T7 (Zero-Root Dockerfiles, Caddy 2 SSE Gateway, Compose & README)
```

---

## Task Breakdown

### `T1`: Backend Foundation, Pydantic v2 SSE Contracts, Audio Sanitizer & Temp Cleanup
- **Covers Spec IDs:** `S1`, `S2`
- **Dependencies:** `None`
- **Route:** `inline`
- **Risk Tier:** `high (security/input validation & file-system cleanup boundary)`
- **Target Modules / Files:**
  - `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pyproject.toml`
  - `backend/app/__init__.py`, `backend/app/config.py`
  - `backend/app/schemas/__init__.py`, `backend/app/schemas/events.py`, `backend/app/schemas/requests.py`
  - `backend/app/services/audio/__init__.py`, `backend/app/services/audio/validator.py`, `backend/app/services/audio/cleanup.py`
  - `backend/tests/conftest.py`, `backend/tests/test_audio_validator.py`
- **Acceptance Criteria:**
  - [x] RED test written and observed failing in `backend/tests/test_audio_validator.py` for `S1` (extension, MIME, magic-byte validation for `.mp3`/`.wav`/`.m4a`/`.ogg`, and `25 MB` size cap) and `S2` (guaranteed temp file unlink on normal exit, exception, and async generator cancellation).
  - [x] Minimal implementation passes GREEN with strict Pydantic v2 models (`StatusEventPayload`, `TranscriptChunkPayload`, `LLMTokenPayload`, `ErrorEventPayload`, `format_sse`).
  - [x] Zero orphan files remain in temporary storage after test runs.
- **Verification Command:** `cd backend && .venv/bin/pytest tests/test_audio_validator.py -v && .venv/bin/ruff check app tests && .venv/bin/mypy app tests`
- **Status:** `[x] done` (2026-11-02, Claude Code — 53 tests green; ruff, ruff format, mypy --strict clean)

---

### `T2`: Dual-Mode ASR Strategy Engine (`LocalWhisperASR` CPU INT8 + `ApiWhisperASR`)
- **Covers Spec IDs:** `S3`, `S4`
- **Dependencies:** `T1`
- **Route:** `sub-agent`
- **Risk Tier:** `medium (concurrency / async thread-queue bridge & external API contract)`
- **Target Modules / Files:**
  - `backend/app/services/asr/__init__.py`
  - `backend/app/services/asr/base.py`
  - `backend/app/services/asr/local_whisper.py`
  - `backend/app/services/asr/api_whisper.py`
  - `backend/app/services/asr/factory.py`
  - `backend/tests/test_asr_strategies.py`
- **Acceptance Criteria:**
  - [ ] RED test written and observed failing in `backend/tests/test_asr_strategies.py` for `S3` (`faster-whisper` singleton initialized with `device="cpu"`, `compute_type="int8"`, `vad_filter=True`, yielding `TranscriptChunkPayload` asynchronously without blocking the event loop, plus empty/silent audio detection) and `S4` (`ApiWhisperASR` via mocked `AsyncInferenceClient` / OpenAI audio endpoint).
  - [ ] Minimal implementation passes GREEN without downloading live Whisper model weights during `pytest`.
- **Verification Command:** `cd backend && .venv/bin/pytest tests/test_asr_strategies.py -v && .venv/bin/ruff check app tests && .venv/bin/mypy app tests`
- **Status:** `[ ] pending`

---

### `T3`: Multi-Provider LLM Minutes Synthesizer & Prompt Engine
- **Covers Spec IDs:** `S5`
- **Dependencies:** `T1`
- **Route:** `sub-agent`
- **Risk Tier:** `medium (external streaming API integration & prompt formatting invariants)`
- **Target Modules / Files:**
  - `backend/app/services/llm/__init__.py`
  - `backend/app/services/llm/prompts.py`
  - `backend/app/services/llm/synthesizer.py`
  - `backend/tests/test_llm_synthesizer.py`
- **Acceptance Criteria:**
  - [ ] RED test written and observed failing in `backend/tests/test_llm_synthesizer.py` for `S5` (provider resolution across `huggingface`, `openrouter`, and `gemini` base URLs; Executive Minutes system/user prompt structure; streaming token emission; outer ` ```markdown ` fence stripping; and upstream quota/auth error translation).
  - [ ] Minimal implementation passes GREEN using mocked `AsyncOpenAI` chat completion streams.
- **Verification Command:** `cd backend && .venv/bin/pytest tests/test_llm_synthesizer.py -v && .venv/bin/ruff check app tests && .venv/bin/mypy app tests`
- **Status:** `[ ] pending`

---

### Checkpoint 1: Core AI Engine & Domain Services Complete (`After T1-T3`)
- [ ] All unit tests in `backend/tests/` pass (`S1`–`S5`).
- [ ] `ruff` and `mypy` report zero issues on `backend/app`.

---

### `T4`: FastAPI SSE Streaming Endpoint, BYOK Rate Limiter & Bundled Demo Sample
- **Covers Spec IDs:** `S6`, `S7`, `S8`
- **Dependencies:** `T1`, `T2`, `T3`
- **Route:** `inline`
- **Risk Tier:** `high (public API contract, BYOK credential handling, rate limiting & SSE lifecycle)`
- **Target Modules / Files:**
  - `backend/assets/denver_council_sample.mp3`
  - `backend/app/main.py`, `backend/app/dependencies.py`
  - `backend/app/api/__init__.py`, `backend/app/api/rate_limit.py`
  - `backend/app/api/routes/__init__.py`, `backend/app/api/routes/health.py`, `backend/app/api/routes/minutes.py`
  - `backend/tests/test_rate_limit.py`, `backend/tests/test_minutes_sse_api.py`
- **Acceptance Criteria:**
  - [ ] RED tests written and observed failing in `test_rate_limit.py` and `test_minutes_sse_api.py` for `S6` (ordered SSE events: `uploading` -> `transcribing` -> `transcript_chunk` -> `analyzing` -> `llm_token` -> `completed`), `S7` (per-IP 429 rate limit on server fallback vs. BYOK header bypass), and `S8` (`GET /api/sample-audio` and `POST /api/minutes/generate` with `use_sample=true` preserving the read-only sample asset).
  - [ ] Minimal implementation passes GREEN; full backend test suite, `ruff`, and `mypy` pass with zero errors.
- **Verification Command:** `cd backend && .venv/bin/pytest -v --tb=short && .venv/bin/ruff check app tests && .venv/bin/mypy app tests`
- **Status:** `[ ] pending`

---

### Checkpoint 2: Backend API Complete (`After T4`)
- [ ] All backend unit and integration tests pass (`S1`–`S8`).
- [ ] `GET /api/health`, `GET /api/sample-audio`, and `POST /api/minutes/generate` contracts verified.

---

### `T5`: Next.js App Router Foundation, SSE Stream Hook, Upload Zone & Timestamp Audio Player
- **Covers Spec IDs:** `S8`, `S9`, `S10` (stream parsing & upload/player half)
- **Dependencies:** `T4`
- **Route:** `sub-agent`
- **Risk Tier:** `medium (chunk-buffered SSE stream parsing & HTML5 audio synchronization)`
- **Target Modules / Files:**
  - `frontend/package.json`, `frontend/tsconfig.json`, `frontend/next.config.ts`, `frontend/postcss.config.mjs`
  - `frontend/src/types/api.ts`
  - `frontend/src/hooks/useMinutesStream.ts`
  - `frontend/src/components/Header.tsx`, `frontend/src/components/AudioUploader.tsx`, `frontend/src/components/AudioPlayer.tsx`
  - `frontend/tests/sseParser.test.ts`
- **Acceptance Criteria:**
  - [ ] RED test written and observed failing in `frontend/tests/sseParser.test.ts` verifying chunk-buffered SSE frame parsing across arbitrary chunk boundaries (`status`, `transcript_chunk`, `llm_token`, `error`).
  - [ ] `AudioUploader` validates extension and `25 MB` limit client-side and supports one-click "Instant Demo Mode" (`S8`, `S9`).
  - [ ] `AudioPlayer` exposes an imperative seek handle (`seekTo(seconds)`) that sets `currentTime` and plays.
- **Verification Command:** `cd frontend && npm test -- --run && npx tsc --noEmit`
- **Status:** `[ ] pending`

---

### `T6`: Split-View Transcript/Minutes Workspace, Stepper, BYOK Modal & `.md`/`.pdf` Export
- **Covers Spec IDs:** `S9`, `S10`, `S11`
- **Dependencies:** `T5`
- **Route:** `sub-agent`
- **Risk Tier:** `medium (real-time Markdown rendering, print/PDF export & client BYOK header wiring)`
- **Target Modules / Files:**
  - `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/globals.css`
  - `frontend/src/components/PipelineStepper.tsx`
  - `frontend/src/components/TranscriptPanel.tsx`
  - `frontend/src/components/MinutesPanel.tsx`
  - `frontend/src/components/ExportToolbar.tsx`
  - `frontend/src/components/ByokModal.tsx`
- **Acceptance Criteria:**
  - [ ] `PipelineStepper` reflects live SSE `PipelineStage` transitions (`1. Upload` -> `2. ASR Transcription` -> `3. LLM Synthesis` -> `4. Minutes Ready`) (`S10`).
  - [ ] `TranscriptPanel` renders `[MM:SS - MM:SS]` clickable badges that invoke `AudioPlayer.seekTo(start)` (`S9`).
  - [ ] `MinutesPanel` renders streaming Markdown via `react-markdown` + `remark-gfm` with smooth typing indicator and dark-mode styling (`S10`).
  - [ ] `ExportToolbar` supports Copy to Clipboard, `.md` file download, and clean `.pdf` print/export; `ByokModal` configures provider/model/API key headers (`S11`).
  - [ ] Next.js standalone production build (`npm run build`), `tsc --noEmit`, and `npm run lint` pass with zero errors.
- **Verification Command:** `cd frontend && npm test -- --run && npx tsc --noEmit && npm run lint && npm run build`
- **Status:** `[ ] pending`

---

### Checkpoint 3: Fullstack Application Logic Complete (`After T5-T6`)
- [ ] Backend `pytest` suite passes (`S1`–`S8`).
- [ ] Frontend tests, TypeScript check, lint, and standalone production build pass (`S9`–`S11`).

---

### `T7`: Zero-Root Multi-Stage Dockerfiles, Caddy 2 SSE Gateway, Docker Compose & Portfolio README
- **Covers Spec IDs:** `S12`
- **Dependencies:** `T4`, `T6`
- **Route:** `inline`
- **Risk Tier:** `high (container security, non-root UIDs, reverse-proxy SSE unbuffered streaming)`
- **Target Modules / Files:**
  - `backend/Dockerfile`
  - `frontend/Dockerfile`
  - `caddy/Dockerfile`, `caddy/Caddyfile`
  - `docker-compose.yml`, `.env.example`
  - `README.md`
- **Acceptance Criteria:**
  - [ ] `backend/Dockerfile` uses `python:3.12-slim`, installs `ffmpeg` with `--no-install-recommends`, cleans apt lists, and runs as non-root `UID 1001` (`S12`).
  - [ ] `frontend/Dockerfile` uses `node:22-alpine` multi-stage standalone build and runs as non-root `UID 1001` (`S12`).
  - [ ] `caddy/Dockerfile` and `caddy/Caddyfile` run Caddy 2 as a non-root user on port `8080`, enforcing `request_body { max_size 30MB }`, `flush_interval -1`, and `read_timeout 300s` on `/api/*` (`S12`).
  - [ ] `README.md` includes Mermaid architecture and sequence diagrams, explanation of technical decisions (SSE, CPU INT8 ASR, Zero-Root containers, Caddy 2 gateway), and single-command quickstart (`docker compose up --build`).
  - [ ] `docker compose config -q` validates cleanly and all test/lint suites remain green.
- **Verification Command:** `docker compose config -q && (cd backend && .venv/bin/pytest -v) && (cd frontend && npm test -- --run && npx tsc --noEmit)`
- **Status:** `[ ] pending`
