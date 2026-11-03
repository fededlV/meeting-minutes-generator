# Domain Glossary (`GLOSSARY.md`)

> Canonical definitions of domain terms, entities, and bounded-context concepts for **AI Meeting Minutes Generator**.  
> Both Antigravity (specs) and Claude Code (implementation) must use these exact terms consistently in specs, code symbols, APIs, and tests.

| Term | Definition | Aliases to Avoid | Bounded Context / Module |
|---|---|---|---|
| `AudioUpload` | A user-supplied or demo-loaded meeting audio file validated against allowed extensions (`.mp3`, `.wav`, `.m4a`, `.ogg`), MIME type, magic-byte header, and the `25 MB` size cap. | `SoundFile`, `VoiceClip`, `MediaBlob` | `backend/app/services/audio` |
| `DemoSample` | The pre-bundled excerpt of a Denver City Council meeting (`denver_council_sample.mp3`) exposed for one-click Instant Demo Mode testing through the real pipeline. | `MockAudio`, `FakeClip`, `TestTrack` | `backend/assets` & `frontend` |
| `ASRStrategy` | Abstract asynchronous interface (`transcribe(file_path: Path) -> AsyncIterator[TranscriptChunkPayload]`) encapsulating speech-to-text execution. | `TranscriberEngine`, `SpeechRecognizer` | `backend/app/services/asr` |
| `LocalWhisperASR` | Concrete `ASRStrategy` using `faster-whisper` (`base.en` or `small.en`) on `device="cpu"` with `compute_type="int8"` and `vad_filter=True` to stay under `1.5 GB` RAM. | `CpuWhisper`, `OfflineASR` | `backend/app/services/asr` |
| `ApiWhisperASR` | Concrete `ASRStrategy` offloading transcription to Hugging Face Serverless Inference API (`InferenceClient`) or an OpenAI-compatible audio transcriptions endpoint. | `RemoteWhisper`, `CloudASR` | `backend/app/services/asr` |
| `TranscriptChunkPayload` | A single timestamped segment emitted lazily by `ASRStrategy` containing `start` (float seconds), `end` (float seconds), and `text` (trimmed string). | `SubtitleLine`, `CaptionItem`, `Utterance` | `backend/app/schemas` & `frontend/src/types` |
| `LLMProvider` | Enumerated target inference service (`huggingface`, `openrouter`, `gemini`) accessed via the OpenAI-compatible `AsyncOpenAI` SDK (`chat.completions.create(..., stream=True)`). | `ModelVendor`, `AIBackend` | `backend/app/services/llm` |
| `MinutesSynthesizer` | Service that consumes the assembled transcript and streams raw Markdown tokens covering Executive Summary, Discussion Points, Takeaways, and Action Items without outer code fences. | `SummaryGenerator`, `NoteTaker` | `backend/app/services/llm` |
| `SSEEvent` | Server-Sent Event frame emitted by `POST /api/minutes/generate` with one of four discriminated event types: `status`, `transcript_chunk`, `llm_token`, or `error`. | `StreamMessage`, `WebhookEvent`, `SocketFrame` | `backend/app/api` & `frontend/src/hooks` |
| `PipelineStage` | Discrete lifecycle state reported via `event: status`: `uploading`, `transcribing`, `analyzing`, or `completed`. | `JobPhase`, `WorkflowStep` | `backend/app/schemas` & `frontend/src/components` |
| `BYOKCredentials` | Optional request-scoped headers (`X-API-Key`, `X-HF-Token`, `X-LLM-Provider`, `X-LLM-Model`) provided by the client to authenticate inference calls directly and bypass server fallback IP rate limits. | `UserToken`, `CustomAuth` | `backend/app/api` & `frontend/src/components` |
