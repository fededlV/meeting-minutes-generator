# Project Agent Rules (`AGENTS.md`)

> This file defines project-specific commands, structure, conventions, and boundaries for **AI Meeting Minutes Generator**.  
> It supplements `~/.config/ai-workflow/GLOBAL_RULES.md` and must never weaken the `Status: Approved` spec gate.

## Commands

Exact project commands used by Claude Code for TDD, verification, and builds:

- **Install / Setup (Backend):** `cd backend && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
- **Install / Setup (Frontend):** `cd frontend && npm ci`
- **Test (All Backend):** `cd backend && .venv/bin/pytest -v --tb=short`
- **Test (Single / Focused Backend):** `cd backend && .venv/bin/pytest <path> -k <test_name> -v`
- **Test (Frontend):** `cd frontend && npm test -- --run`
- **Typecheck (Backend):** `cd backend && .venv/bin/mypy app tests`
- **Typecheck (Frontend):** `cd frontend && npx tsc --noEmit`
- **Lint / Format Check (Backend):** `cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests`
- **Lint / Format Check (Frontend):** `cd frontend && npm run lint`
- **Build (Frontend):** `cd frontend && npm run build`
- **Build & Verify Containers:** `docker compose config -q && docker compose build`

## Structure

Key directories and architectural boundaries:

- `backend/app/`: FastAPI application (`main.py`, `config.py`, `dependencies.py`)
  - `backend/app/schemas/`: Strict Pydantic v2 contracts for REST endpoints, SSE events, and BYOK headers
  - `backend/app/services/asr/`: Strategy pattern ASR engine (`base.py`, `local_whisper.py`, `api_whisper.py`, `factory.py`)
  - `backend/app/services/llm/`: OpenAI-compatible multi-provider LLM synthesizer (`client.py`, `prompts.py`)
  - `backend/app/services/audio/`: Audio upload validation, magic-byte inspection, sample loader, and guaranteed temp-file cleanup (`validator.py`, `cleanup.py`)
  - `backend/app/api/`: Route handlers (`routes/minutes.py`, `routes/health.py`) and sliding-window IP rate limiter (`rate_limit.py`)
  - `backend/assets/`: Bundled Denver City Council sample audio clip (`denver_council_sample.mp3`)
- `backend/tests/`: Automated `pytest`, `pytest-asyncio`, and `respx` unit and integration test suites
- `frontend/src/`: Next.js (App Router) + TypeScript + Tailwind CSS application
  - `frontend/src/app/`: App Router root (`layout.tsx`, `page.tsx`, `globals.css`)
  - `frontend/src/components/`: Cohesive UI modules (`AudioUploader.tsx`, `AudioPlayer.tsx`, `PipelineStepper.tsx`, `TranscriptPanel.tsx`, `MinutesPanel.tsx`, `ByokModal.tsx`, `ExportToolbar.tsx`)
  - `frontend/src/hooks/`: SSE streaming hook (`useMinutesStream.ts`)
  - `frontend/src/types/`: Strict TypeScript discriminated unions mirroring backend SSE & REST contracts (`api.ts`)
- `caddy/`: Caddy 2 gateway configuration (`Caddyfile`) and non-root container setup
- `specs/`: Change specifications (`specs/<change>/{spec.md,tasks.md,handoff.md}`)
- `docs/adr/`: Architectural Decision Records (`NNNN-<slug>.md`)
- `GLOSSARY.md`: Ubiquitous domain language definitions

## Style & Conventions

- Follow SOLID, separation of concerns, and explicit module interfaces (`Protocol` / ABCs in Python, strict TypeScript interfaces in frontend).
- Validate all external inputs at system boundaries using **Pydantic v2** (`model_config = ConfigDict(extra="forbid", strict=True)` where applicable) and file magic-byte verification.
- Keep functions small, cohesive, and free of hidden global mutable state; manage heavy resources (like local `WhisperModel`) via lazy singleton dependency injection (`app.state` / FastAPI `Depends`).
- Use async generators (`AsyncIterator`) with `yield` for both ASR segment emission and LLM token streaming to keep RAM below `1.5 GB`.
- Never surround generated LLM Markdown meeting minutes with outer ` ```markdown ` fences; enforce clean Markdown via system prompt and stream-level fence stripping.

## Testing

- **Default:** Test-Driven Development (Red -> Green -> Refactor) using the commands in `## Commands`.
- Assert observable behaviour through public interfaces, covering happy paths, edge cases, and failure modes.
- External services (Hugging Face, OpenRouter, Google AI Studio, and `faster-whisper` model loading) must be isolated in CI/CD tests using `respx` or `unittest.mock` deterministic fakes; never download multi-hundred-MB weights or hit live external APIs during `pytest`.

## Boundaries

- **Always:**
  - Require `specs/<change>/spec.md` with `Status: Approved` before writing implementation code.
  - Run focused tests and lint/typecheck from `## Commands` before committing each work unit.
  - Delete temporary uploaded audio files inside `finally` blocks so zero orphan files remain on disk after stream completion, cancellation, or error.
  - Run all Docker containers (`backend`, `frontend`, `caddy`) as non-root users (`UID 1001` for apps, non-root user for Caddy).
  - Use Conventional Commits (`<= 400` changed lines per slice) without AI attribution.
- **Ask First:**
  - Adding new third-party dependencies beyond those specified in `specs/<change>/spec.md` or upgrading major framework versions.
  - Changing public REST/SSE contracts or security/rate-limit rules.
  - Modifying container network topology or environment variable contracts.
- **Never:**
  - Commit secrets, `.env` files, credentials, or API tokens.
  - Log user-supplied BYOK tokens (`X-API-Key`, `X-HF-Token`) in application or proxy logs.
  - Bypass or weaken tests, linters, or the `Status: Approved` spec gate.

## Definition of Done

- [ ] Every requirement (`S#`) in `specs/<change>/spec.md` is satisfied and verified by automated tests.
- [ ] All `Test`, `Typecheck`, `Lint`, and `Build` commands in `## Commands` pass with zero errors.
- [ ] Edge cases, error paths, and regressions on shared code paths are covered.
- [ ] `specs/<change>/tasks.md` and `specs/<change>/handoff.md` are updated with final status and commits.
- [ ] Architectural decisions are recorded in `docs/adr/` and saved to Engram.
