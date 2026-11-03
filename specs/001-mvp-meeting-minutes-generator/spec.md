# Specification: AI Meeting Minutes Generator (End-to-End Fullstack Application)

- **Change ID:** `001-mvp-meeting-minutes-generator`
- **Status:** `Approved`
- **Approved By:** `fede (Human)`
- **Approval Date:** `2026-11-01`
- **Author Agent:** Antigravity (Gemini)

---

## 1. Objective

Transform a GPU-bound Jupyter Notebook prototype for meeting transcription and summarization into a production-grade, decoupled, containerized fullstack web application (**AI Meeting Minutes Generator**) optimized to run on CPU-only hardware (`< 1.5 GB` RAM) and free-tier LLM endpoints.

- **Target Users:** Technical recruiters, engineering evaluators, and end-users who need to upload a meeting recording (or click a single "Instant Demo Mode" button with a pre-bundled Denver City Council excerpt) and receive real-time timestamped transcription alongside structured executive meeting minutes.
- **System Outcome:**
  1. **Stage 1 — Automatic Speech Recognition (ASR):** Accepts `.mp3`, `.wav`, `.m4a`, or `.ogg` audio up to `25 MB`, validates extensions/MIME/magic bytes, and lazily yields timestamped transcript segments (`[MM:SS - MM:SS]`) via either local CPU `faster-whisper` (`int8` + Silero VAD) or external serverless Whisper APIs.
  2. **Stage 2 — Executive Minutes Synthesis (LLM):** Streams the assembled transcript into an OpenAI-compatible instruction-tuned LLM (`huggingface`, `openrouter`, or `gemini`) to generate clean Markdown minutes (without outer code fences) containing **Executive Summary**, **Discussion Points**, **Takeaways**, and **Action Items**.
  3. **Real-Time UX & Zero-Root Delivery:** Streams `status`, `transcript_chunk`, `llm_token`, and `error` Server-Sent Events (SSE) through a Caddy 2 reverse proxy (`flush_interval -1`) to a Next.js (App Router) split-pane UI featuring interactive audio timestamp seeking, BYOK credential configuration, and `.md`/`.pdf` export.

---

## 2. Assumptions

- `A1 (Gateway):` **Caddy 2** (`caddy:2-alpine`) replaces NGINX as the sole reverse proxy and public entry point, using native `Caddyfile` directives (`flush_interval -1`, `request_body { max_size 30MB }`, `read_timeout 300s`).
- `A2 (Frontend Stack):` **Next.js (App Router)** with TypeScript and Tailwind CSS is compiled with `output: "standalone"` in a multi-stage `node:22-alpine` Dockerfile and runs as non-root `UID 1001`.
- `A3 (Default Runtime Mode):` Out-of-the-box `ASR_MODE` defaults to `local` using `faster-whisper` (`base.en`, `device="cpu"`, `compute_type="int8"`, `vad_filter=True`), allowing Stage 1 transcription to work with zero external API keys.
- `A4 (Demo Sample Execution):` Instant Demo Mode loads a real bundled audio excerpt (`denver_council_sample.mp3`, `<= 2 MB`, ~30–60s of speech) into the frontend `<audio>` player and submits it through the live ASR + LLM SSE pipeline.
- `A5 (LLM Key Resolution):` Stage 2 resolves credentials in strict precedence order: request BYOK header (`X-API-Key` or `X-HF-Token`) -> environment variable (`LLM_API_KEY` / provider-specific env var). If neither is present, Stage 2 emits a structured SSE `error` event (`code: "MISSING_API_KEY"`) prompting the user to configure a free key in the BYOK modal.
- `A6 (Stateless Execution):` No database or persistent server-side file storage is used; uploaded audio files exist only in a restricted temporary directory for the duration of the active request generator and are unconditionally unlinked in a `finally` block.

---

## 3. Tech Stack & Commands

Inherited from [AGENTS.md](file:///home/fede/Proyectos/meeting-minutes-generator/AGENTS.md):

- **Backend Runtime / Stack:** Python `3.12` (`python:3.12-slim`), FastAPI, Uvicorn, Pydantic v2, `faster-whisper`, `huggingface_hub`, `openai`, `python-multipart`, `httpx`.
- **Frontend Runtime / Stack:** Node.js `22` (`node:22-alpine`), Next.js 15 (App Router, `output: 'standalone'`), React 19, TypeScript, Tailwind CSS, `lucide-react`, `react-markdown`, `remark-gfm`.
- **Gateway / Infrastructure:** Docker Compose, Caddy 2 (`caddy:2-alpine`), `ffmpeg` (backend system dependency).
- **Test (All Backend):** `cd backend && .venv/bin/pytest -v --tb=short`
- **Test (Single / Focused Backend):** `cd backend && .venv/bin/pytest <path> -k <test_name> -v`
- **Test (Frontend):** `cd frontend && npm test -- --run`
- **Typecheck (Backend):** `cd backend && .venv/bin/mypy app tests`
- **Typecheck (Frontend):** `cd frontend && npx tsc --noEmit`
- **Lint / Format Check (Backend):** `cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests`
- **Lint / Format Check (Frontend):** `cd frontend && npm run lint`
- **Build (Frontend):** `cd frontend && npm run build`
- **Container Config & Build Check:** `docker compose config -q && docker compose build`

---

## 4. Project Structure, Capability Map & Module Boundaries

### 4.1. Capability Map

| Module ID | Responsibility | Depends On |
|---|---|---|
| `core-contracts-config` | Pydantic v2 REST/SSE schemas, environment settings, audio validator/cleanup, and IP rate limiter | — |
| `asr-engine` | Strategy pattern ASR (`LocalWhisperASR` on CPU INT8 + `ApiWhisperASR` via HF/OpenAI API) yielding `TranscriptChunkPayload` | `core-contracts-config` |
| `llm-synthesizer` | OpenAI-compatible multi-provider streaming client (`huggingface`, `openrouter`, `gemini`) and executive minutes prompt engine | `core-contracts-config` |
| `fastapi-sse-api` | `GET /api/health`, `GET /api/sample-audio`, and `POST /api/minutes/generate` SSE streaming pipeline + `pytest` suite | `core-contracts-config`, `asr-engine`, `llm-synthesizer` |
| `nextjs-ui` | Next.js App Router UI: Drag-and-drop uploader, Instant Demo loader, timestamp-synced `<audio>` player, SSE stepper, split-view transcript + Markdown minutes, BYOK modal, `.md`/`.pdf` export | `fastapi-sse-api` |
| `docker-caddy-infra` | Non-root multi-stage Dockerfiles (`backend`, `frontend`), `caddy/Caddyfile` with zero-buffering SSE rules, `docker-compose.yml`, and portfolio `README.md` | `fastapi-sse-api`, `nextjs-ui` |

**Build Order:** `core-contracts-config` -> `asr-engine`, `llm-synthesizer` -> `fastapi-sse-api` -> `nextjs-ui` -> `docker-caddy-infra`

### 4.2. Repository Directory Tree

```text
meeting-minutes-generator/
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── GLOSSARY.md
├── README.md
├── .env.example
├── docker-compose.yml
├── caddy/
│   ├── Dockerfile
│   └── Caddyfile
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml
│   ├── assets/
│   │   └── denver_council_sample.mp3
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── events.py
│   │   │   └── requests.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── audio/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── validator.py
│   │   │   │   └── cleanup.py
│   │   │   ├── asr/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── local_whisper.py
│   │   │   │   ├── api_whisper.py
│   │   │   │   └── factory.py
│   │   │   └── llm/
│   │   │       ├── __init__.py
│   │   │       ├── prompts.py
│   │   │       └── synthesizer.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── rate_limit.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           ├── health.py
│   │           └── minutes.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_audio_validator.py
│       ├── test_asr_strategies.py
│       ├── test_llm_synthesizer.py
│       ├── test_rate_limit.py
│       └── test_minutes_sse_api.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── postcss.config.mjs
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── types/
│   │   │   └── api.ts
│   │   ├── hooks/
│   │   │   └── useMinutesStream.ts
│   │   └── components/
│   │       ├── Header.tsx
│   │       ├── AudioUploader.tsx
│   │       ├── AudioPlayer.tsx
│   │       ├── PipelineStepper.tsx
│   │       ├── TranscriptPanel.tsx
│   │       ├── MinutesPanel.tsx
│   │       ├── ExportToolbar.tsx
│   │       └── ByokModal.tsx
│   └── tests/
│       └── sseParser.test.ts
├── docs/
│   └── adr/
│       ├── 0000-template.md
│       ├── 0001-dual-mode-asr-strategy-and-cpu-int8-optimization.md
│       ├── 0002-multi-provider-llm-routing-and-byok-rate-limiting.md
│       └── 0003-sse-streaming-pipeline-and-caddy2-reverse-proxy.md
└── specs/
    └── 001-mvp-meeting-minutes-generator/
        ├── spec.md
        ├── tasks.md
        └── handoff.md
```

---

## 5. Code Style & Strict Contracts

### 5.1. Backend Pydantic v2 & SSE Event Contracts (`backend/app/schemas/events.py`)

```python
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PipelineStage(StrEnum):
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"


class ASRMode(StrEnum):
    LOCAL = "local"
    API = "api"


class LLMProvider(StrEnum):
    HUGGINGFACE = "huggingface"
    OPENROUTER = "openrouter"
    GEMINI = "gemini"


class StatusEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: PipelineStage
    message: str = Field(min_length=1, max_length=280)


class TranscriptChunkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: float = Field(ge=0.0, description="Segment start timestamp in seconds")
    end: float = Field(ge=0.0, description="Segment end timestamp in seconds")
    text: str = Field(min_length=1, description="Transcribed segment text")

    @model_validator(mode="after")
    def validate_time_range(self) -> "TranscriptChunkPayload":
        if self.end < self.start:
            raise ValueError(f"end timestamp ({self.end}) must be >= start timestamp ({self.start})")
        return self


class LLMTokenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token: str = Field(description="Single token or fragment emitted by the LLM")


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_AUDIO_FORMAT = "INVALID_AUDIO_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    MISSING_API_KEY = "MISSING_API_KEY"
    ASR_FAILURE = "ASR_FAILURE"
    LLM_QUOTA_OR_UPSTREAM_ERROR = "LLM_QUOTA_OR_UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: ErrorCode
    message: str
    recoverable: bool = True


def format_sse(
    event: Literal["status", "transcript_chunk", "llm_token", "error"],
    payload: BaseModel,
) -> str:
    """Serialize a Pydantic payload into a standard W3C Server-Sent Event frame."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"
```

### 5.2. Strategy Protocols & Executive Minutes Prompt Contract

```python
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from app.schemas.events import TranscriptChunkPayload


class ASRStrategy(Protocol):
    async def transcribe(self, audio_path: Path) -> AsyncIterator[TranscriptChunkPayload]:
        """Lazily yield timestamped transcript segments from a validated audio file."""
        ...
```

**Mandatory Executive Minutes Prompt Contract (`backend/app/services/llm/prompts.py`):**
- **System Prompt:** Instructs the model to act as an expert Executive Secretary and produce formal meeting minutes in **clean GitHub-Flavored Markdown** without wrapping the response in outer ` ```markdown ` or ` ``` ` code blocks.
- **Required Markdown Headings (exact structure):**
  1. `## Executive Summary` (Identified attendees, location, date/context of the meeting, and high-level purpose; explicitly noting `"Not specified in audio"` when a field is not mentioned rather than hallucinating).
  2. `## Discussion Points` (Bulleted breakdown of key topics and arguments addressed).
  3. `## Takeaways` (Core ideas, decisions, and reached consensus).
  4. `## Action Items` (Markdown table or structured task list specifying owner/responsible party, action description, and any stated deadline).

### 5.3. REST Endpoints & Request Headers Contract

| Method & Path | Request Contract | Response Contract | Error Behavior |
|---|---|---|---|
| `GET /api/health` | None | `200 OK` JSON: `{"status": "ok", "asr_mode": "local"\|"api", "default_llm_provider": "huggingface"\|"openrouter"\|"gemini"}` | `500` on unexpected startup fault |
| `GET /api/sample-audio` | None | `200 OK` `audio/mpeg` binary stream of `denver_council_sample.mp3` (with `Content-Disposition` & `Accept-Ranges: bytes`) | `404` if sample asset is missing |
| `POST /api/minutes/generate` | `multipart/form-data`: `file` (`UploadFile`, optional if `use_sample=true`) OR `use_sample` (`bool = false`). Optional headers: `X-API-Key`, `X-HF-Token`, `X-LLM-Provider`, `X-LLM-Model`, `X-ASR-Mode` | `200 OK` `text/event-stream` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`) streaming `status`, `transcript_chunk`, `llm_token`, `error` events | Pre-stream validation errors (`413`, `415`, `422`, `429`) return structured JSON `{ "error": { "code": "...", "message": "..." } }`; mid-stream failures emit `event: error` SSE frame |

### 5.4. Caddy 2 Reverse Proxy Contract (`caddy/Caddyfile`)

```caddyfile
:8080 {
    request_body {
        max_size 30MB
    }

    handle /api/* {
        reverse_proxy backend:8000 {
            flush_interval -1
            transport http {
                read_timeout 300s
                write_timeout 300s
            }
        }
    }

    handle /* {
        reverse_proxy frontend:3000
    }
}
```

---

## 6. Acceptance Criteria (Behavioural & Testable)

Every requirement `S#` is deterministic, observable, and falsifiable by an automated test:

- **`S1` (Audio Extension, MIME, Magic-Byte & Size Validation):**
  - **Given:** A client submits `POST /api/minutes/generate` with an uploaded file.
  - **When:** The file extension is not in `{.mp3, .wav, .m4a, .ogg}`, OR the declared MIME type is outside `audio/*` / `application/octet-stream`, OR the leading file magic bytes do not match valid MP3 (`ID3` or MPEG frame sync `0xFFFB` / `0xFFFA` / `0xFFF3` / `0xFFF2` / `0xFFE3` / `0xFFE2`), WAV (`RIFF....WAVE`), M4A (`ftyp`), or OGG (`OggS`) signatures, OR the payload size exceeds `25 MB` (`26,214,400` bytes).
  - **Then:** The endpoint rejects the upload before invoking ASR, returns HTTP `415` (invalid format/magic bytes) or HTTP `413` (exceeds `25 MB`) with structured JSON `{ "error": { "code": "INVALID_AUDIO_FORMAT" | "FILE_TOO_LARGE", "message": "..." } }`, and leaves zero files in the temporary directory.

- **`S2` (Guaranteed Temporary File Sanitization & Cleanup):**
  - **Given:** A valid audio upload is written to a randomized UUID filename (`<uuid4>.<ext>`) inside the restricted temp directory (`tempfile.gettempdir()`).
  - **When:** The SSE stream finishes normally (`completed`), raises an ASR/LLM exception mid-stream, or the client disconnects early (`asyncio.CancelledError` / generator `.aclose()`).
  - **Then:** The `finally` block in the streaming pipeline unconditionally unlinks the temporary file so that `audio_path.exists()` is `False` immediately after the generator exits.

- **`S3` (Local CPU ASR Strategy with `faster-whisper` INT8 & VAD):**
  - **Given:** `ASR_MODE=local` (or `X-ASR-Mode: local`).
  - **When:** `LocalWhisperASR.transcribe(audio_path)` is invoked.
  - **Then:** `WhisperModel` is initialized lazily as a singleton with `model_size_or_path in {"base.en", "small.en"}`, `device="cpu"`, and `compute_type="int8"`; `model.transcribe(..., vad_filter=True)` runs without blocking the asyncio loop and yields `TranscriptChunkPayload(start, end, text)` segments lazily as each non-empty segment is decoded.

- **`S4` (Serverless / External API ASR Strategy):**
  - **Given:** `ASR_MODE=api` (or `X-ASR-Mode: api`) and a valid API token (`X-HF-Token`, `X-API-Key`, or server `HF_TOKEN`).
  - **When:** `ApiWhisperASR.transcribe(audio_path)` is invoked.
  - **Then:** The service calls the configured remote Whisper endpoint (`huggingface_hub.AsyncInferenceClient` or OpenAI-compatible audio transcriptions API) without loading `faster-whisper` into local RAM, yielding normalized `TranscriptChunkPayload` objects.

- **`S5` (Multi-Provider OpenAI-Compatible LLM Streaming & Fence Stripping):**
  - **Given:** A non-empty transcript assembled from Stage 1 and a target `LLMProvider` (`huggingface`, `openrouter`, or `gemini`).
  - **When:** `MinutesSynthesizer.stream_minutes(transcript, provider, model, api_key)` is invoked.
  - **Then:** `AsyncOpenAI` connects to the provider's exact `base_url` with `stream=True`, sends the Executive Minutes prompt, strips any accidental leading/trailing ` ```markdown ` or ` ``` ` wrapper tokens, and yields raw Markdown string tokens containing `## Executive Summary`, `## Discussion Points`, `## Takeaways`, and `## Action Items`.

- **`S6` (End-to-End SSE Event Ordering & Protocol):**
  - **Given:** A valid request to `POST /api/minutes/generate` (`file` upload or `use_sample=true`).
  - **When:** The client reads the `text/event-stream` response.
  - **Then:** Events arrive in strict lifecycle order:
    1. `event: status` (`stage: "uploading"`)
    2. `event: status` (`stage: "transcribing"`)
    3. One or more `event: transcript_chunk` frames (`{start, end, text}`)
    4. `event: status` (`stage: "analyzing"`)
    5. One or more `event: llm_token` frames (`{token}`)
    6. `event: status` (`stage: "completed"`)

- **`S7` (BYOK Credential Precedence & Per-IP Rate Limiting):**
  - **Given:** A client calls `POST /api/minutes/generate`.
  - **When:** The client omits `X-API-Key` and `X-HF-Token` and exceeds the configured per-IP sliding-window quota (default `5` requests/hour).
  - **Then:** The server returns HTTP `429 Too Many Requests` with `{ "error": { "code": "RATE_LIMIT_EXCEEDED", "message": "..." } }`.
  - **When:** The same IP supplies a non-empty `X-API-Key` or `X-HF-Token` header.
  - **Then:** The request bypasses the IP rate limiter and uses the supplied header credential for upstream inference without logging the secret.

- **`S8` (Instant Demo Mode & Sample Audio Endpoint):**
  - **Given:** A visitor clicks "Load Denver City Council Sample" in the UI.
  - **When:** The frontend fetches `GET /api/sample-audio` for the `<audio>` player and triggers `POST /api/minutes/generate` with `use_sample=true`.
  - **Then:** `GET /api/sample-audio` returns HTTP `200` (`audio/mpeg`) with the bundled sample audio, and `POST /api/minutes/generate` processes the bundled sample through the live ASR + LLM SSE pipeline without deleting the read-only bundled asset in `backend/assets/`.

- **`S9` (Frontend Upload Zone, Validation & Timestamp-Synced Audio Player):**
  - **Given:** The Next.js App Router UI is rendered in the browser.
  - **When:** A user drags and drops an audio file (or loads the demo sample) and clicks a timestamp badge (e.g., `[00:12 - 00:18]`) in the `TranscriptPanel`.
  - **Then:** Files exceeding `25 MB` or with unsupported extensions show an immediate inline validation message prior to upload; valid audio loads into the custom HTML5 `AudioPlayer`, and clicking `[00:12 - 00:18]` sets `audioElement.currentTime = 12` and triggers playback.

- **`S10` (Frontend Real-Time SSE Stepper & Split-View Markdown Rendering):**
  - **Given:** An active SSE stream from `POST /api/minutes/generate`.
  - **When:** `status`, `transcript_chunk`, and `llm_token` events arrive over the `fetch` `ReadableStream`.
  - **Then:** `PipelineStepper` highlights the active step (`1. Upload` -> `2. ASR Transcription` -> `3. LLM Synthesis` -> `4. Minutes Ready`), `TranscriptPanel` appends timestamped segments in the left panel, and `MinutesPanel` renders incoming tokens incrementally in the right panel via `react-markdown` + `remark-gfm` with dark-mode support.

- **`S11` (Export `.md` / `.pdf`, Copy to Clipboard & BYOK Modal):**
  - **Given:** Meeting minutes have been generated in `MinutesPanel`.
  - **When:** The user clicks "Copy", "Download .md", "Export .pdf", or opens the "API Settings (BYOK)" modal.
  - **Then:** "Copy" writes the raw Markdown to `navigator.clipboard`; "Download .md" triggers a browser download of `meeting-minutes-<date>.md`; "Export .pdf" triggers clean print/PDF export of the formatted minutes; and the BYOK modal persists selected provider/model/token in browser storage and attaches `X-API-Key` / `X-HF-Token` / `X-LLM-Provider` / `X-LLM-Model` headers to subsequent generation requests.

- **`S12` (Zero-Root Multi-Stage Containers & Caddy 2 SSE Gateway):**
  - **Given:** `docker compose up --build` is executed.
  - **When:** Evaluating `backend/Dockerfile`, `frontend/Dockerfile`, `caddy/Dockerfile`, `caddy/Caddyfile`, and `docker-compose.yml`.
  - **Then:** `backend` is based on `python:3.12-slim` with only `ffmpeg` installed (`--no-install-recommends`) and runs as `UID 1001`; `frontend` uses a multi-stage `node:22-alpine` build (`output: 'standalone'`) running as `UID 1001`; `caddy` runs as a non-root UID (`101` or `1001`) on port `8080` with `flush_interval -1`, `read_timeout 300s`, and `max_size 30MB`; and only `caddy` exposes a host port while `backend` and `frontend` communicate over an internal bridge network.

---

## 7. Risks, Edge Cases & Failure Modes

- **Boundary / Edge Cases:**
  - **Silent or No-Speech Audio:** If `faster-whisper` with `vad_filter=True` yields zero speech segments (e.g., pure silence upload), Stage 1 emits a fallback notice or `event: error` (`code: "ASR_FAILURE"`, `"No speech detected in audio file"`) and skips calling the LLM to avoid hallucinated minutes.
  - **Path Traversal in Upload Filename:** Original client `UploadFile.filename` is used only to inspect the suffix (`.mp3`, `.wav`, `.m4a`, `.ogg`); the on-disk temporary file always uses a freshly generated `uuid4().hex + ext`.
  - **SSE Frame Fragmentation:** Network chunks read from `ReadableStreamDefaultReader` may split a JSON line across two chunks or coalesce multiple `event:` blocks into one read. `useMinutesStream.ts` must buffer incomplete text up to the last `\n\n` boundary before parsing.
- **External Failure Modes:**
  - **Upstream LLM 401/403/429/5xx Mid-Stream:** Caught inside `MinutesSynthesizer`; converted into a structured `event: error` (`code: "LLM_QUOTA_OR_UPSTREAM_ERROR"`) with actionable guidance (e.g., suggesting switching provider or adding a BYOK token) before cleanly closing the SSE stream.
  - **Blocking Event Loop on CPU ASR:** `faster-whisper`'s `segments` iterator is synchronous C++ execution; iterating it directly in an `async def` generator would freeze FastAPI. It must be iterated in a worker thread pushing segments into an `asyncio.Queue`.
- **Security & Data Integrity:**
  - **Secret Redaction:** `X-API-Key` and `X-HF-Token` headers must never be echoed in error payloads, logs, or tracebacks.
  - **Proxy Header Spoofing (`X-Forwarded-For`):** Rate limiter extracts the client IP safely from the immediate peer or trusted Caddy `X-Forwarded-For` entry.

---

## 8. Testing Strategy

- **Backend Unit Tests (`backend/tests/`):**
  - `test_audio_validator.py`: Covers `S1` and `S2` (valid extensions/magic bytes for MP3/WAV/M4A/OGG, rejected disguised `.exe`/text files, `> 25 MB` rejection, and `finally` temp file deletion on both success and exception).
  - `test_asr_strategies.py`: Covers `S3` and `S4` using `unittest.mock` / `respx` to verify `LocalWhisperASR` (`int8`, `vad_filter=True`, async queue streaming) and `ApiWhisperASR` without downloading Whisper weights in CI.
  - `test_llm_synthesizer.py`: Covers `S5` using mocked `AsyncOpenAI` streaming chunks to verify provider base URLs, system prompt sections, and markdown code-fence stripping.
  - `test_rate_limit.py`: Covers `S7` sliding-window IP quota enforcement and BYOK header bypass.
- **Backend Integration Tests (`backend/tests/test_minutes_sse_api.py`):**
  - Covers `S6`, `S7`, `S8` using `httpx.AsyncClient` (`ASGITransport`) against the FastAPI app with mocked ASR/LLM strategies, asserting exact SSE event sequence (`uploading` -> `transcribing` -> `transcript_chunk` -> `analyzing` -> `llm_token` -> `completed`), mid-stream error SSE emission, and `GET /api/sample-audio` binary delivery.
- **Frontend Verification (`frontend/tests/` & Build):**
  - Covers `S9`, `S10`, `S11` via TypeScript strict check (`npx tsc --noEmit`), ESLint (`npm run lint`), unit tests on the chunk-buffered SSE frame parser (`sseParser.test.ts`), and production standalone build (`npm run build`).
- **Infrastructure Verification:**
  - Covers `S12` via `docker compose config -q` and inspecting non-root `USER` directives and `Caddyfile` settings.

---

## 9. Boundaries & Out of Scope

- **In Scope:**
  - Full backend (`FastAPI`), frontend (`Next.js App Router`), bundled Denver City Council sample audio clip, multi-stage non-root Dockerfiles, Caddy 2 gateway config, `docker-compose.yml`, automated test suites, and portfolio `README.md` with Mermaid diagrams.
- **Out of Scope (Do Not Implement):**
  - Persistent database (PostgreSQL/SQLite/Redis), user accounts, or saved meeting history.
  - Real-time browser microphone recording (`MediaRecorder` / WebSockets).
  - Speaker diarization (`pyannote.audio`) or video file transcoding.
  - GPU/CUDA container builds or NGINX configurations.
- **Ask First:**
  - Adding third-party libraries not listed in Section 3.
  - Changing the SSE event names (`status`, `transcript_chunk`, `llm_token`, `error`) or REST route paths.

---

## 10. Open Questions

- None. All architectural ambiguities (Caddy 2 vs. NGINX, Next.js App Router vs. Vite, and Instant Demo Mode execution) were resolved and confirmed during the `interview-me` alignment phase. Ready for human sign-off.
