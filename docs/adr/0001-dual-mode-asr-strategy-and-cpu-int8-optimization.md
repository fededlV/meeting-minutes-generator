# ADR 0001: Dual-Mode ASR Strategy and CPU INT8 Optimization

- **Status:** Accepted
- **Date:** 2026-10-31
- **Related Spec:** `specs/001-mvp-meeting-minutes-generator/spec.md`

## Context

The original Jupyter Notebook prototype loaded `openai/whisper-medium.en` in FP16 on a CUDA GPU, requiring $> 5\text{ GB}$ of VRAM and heavy PyTorch CUDA dependencies ($> 4\text{ GB}$ image size). To deploy the **AI Meeting Minutes Generator** on free-tier CPU-only cloud instances or developer laptops with strict memory budgets ($< 1.5\text{ GB}$ RAM), we need a speech-to-text architecture that avoids GPU lock-in while still supporting timestamped segment streaming.

## Decision

Implement the **Strategy Pattern** (`ASRStrategy` protocol) in `backend/app/services/asr/` supporting two runtime-configurable modes via `ASR_MODE`:

1. **`local` Mode (Default — `LocalWhisperASR`):**
   - Uses `faster-whisper` (CTranslate2 backend) with `base.en` (default) or `small.en`.
   - Enforces `device="cpu"`, `compute_type="int8"`, and Silero Voice Activity Detection (`vad_filter=True`, `vad_parameters=dict(min_silence_duration_ms=500)`).
   - Iterates lazily over the CTranslate2 segment generator in a background worker thread bridged via `asyncio.Queue` / `anyio` so the FastAPI event loop is never blocked while emitting `TranscriptChunkPayload(start, end, text)` items in real time.
2. **`api` Mode (`ApiWhisperASR`):**
   - Uses `huggingface_hub.AsyncInferenceClient` (or an OpenAI-compatible `/v1/audio/transcriptions` endpoint with `response_format="verbose_json"`) to offload Whisper execution to remote serverless infrastructure when local CPU cycles must be near zero.
   - Normalizes returned timestamp chunks (or falls back to a single segment `[0.0, duration]` if the upstream free endpoint omits granular timestamps) into `TranscriptChunkPayload` objects.

## Alternatives Considered

1. **`faster-whisper` INT8 + Strategy Pattern (Chosen):**
   - *Pros:* $4\times$ faster than standard PyTorch Whisper on CPU, $< 500\text{ MB}$ RAM for `base.en` INT8, yields segments incrementally as audio is decoded, works offline out-of-the-box for Instant Demo Mode.
   - *Cons:* Requires `ffmpeg` system library in the container image (`~80 MB` with `--no-install-recommends`).
2. **Original `transformers` / `openai-whisper` on CPU FP32:**
   - *Rejected:* Exceeds $2.5\text{ GB}$ RAM, blocks for minutes on CPU, and buffers the entire transcription before returning.
3. **External API Only:**
   - *Rejected:* Fails out-of-the-box when running locally without an API token and does not always return incremental segment timestamps on free Hugging Face endpoints.

## Consequences

- **Positive:** Container memory stays well below $1.5\text{ GB}$ RAM; Instant Demo Mode works immediately on CPU; users or deployments on micro-VMs can switch to `ASR_MODE=api` via environment variables or request headers.
- **Negative / Risks:** Because `faster-whisper`'s CTranslate2 generator is synchronous/CPU-bound, `LocalWhisperASR` must iterate it inside `asyncio.to_thread` / threadpool producer feeding an `asyncio.Queue` so SSE `transcript_chunk` events flush immediately to the client without blocking the ASGI loop.
