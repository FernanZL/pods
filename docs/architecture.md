# Architecture & contracts

The product is a **local RAG chatbot over podcast episodes**. In the Library you pick episodes, and each one is processed once: download, diarized transcript, then embeddings in a persistent Chroma index. Everything is stored under `./data`. On later visits you open Chat and ask questions, with no reprocessing. New episodes extend the same index.

```
browser ── nginx (frontend, :8080) ──/api──▶ FastAPI (backend, :8000)
                                              ├─ SQLite  data/app.db
                                              ├─ Chroma  data/chroma/
                                              ├─ files   data/podcasts/<podcast>/<episode>/
                                              └─ in-process JobWorker (asyncio, N concurrent)
                                                   download → transcribe → index   (+ summarize)
```

## Contract files (do not modify; report needed changes instead)
`backend/app/{config,domain,models,schemas,db,storage}.py`, `backend/app/providers/__init__.py`, `backend/app/main.py`, `backend/app/api/meta.py`, `backend/tests/conftest.py`, this document.

## Golden rules for all code
- **Never make real network calls in tests or dev**: no OpenAI, no OpenRouter, no episode downloads. Mock `httpx` with `respx`. Mock the OpenAI SDK by injecting a fake client object. Use `app.providers.fake`.
- All paid work happens only inside JobWorker steps that the user started from the UI.
- Provider objects come from `app.providers.get_llm/get_embedder/get_transcriber`. Never construct `OpenAI()` elsewhere.
- Blocking work (HTTP, ffmpeg, SDK calls) runs inside the worker via `asyncio.to_thread`. API handlers stay fast.
- File paths stored in DB are **relative to `settings.data_dir`** (`storage.to_rel/to_abs`).
- Python 3.12 with type hints, `ruff` clean, line length 100.

## Service function contracts (cross-agent)

These functions are called by `jobs/worker.py` and the API layer. Each one opens its own DB session via `db.session_scope()` and updates the `Episode` row itself. Each one is **idempotent**: if its artifact exists and `force=False`, it returns immediately.

| Module (owner) | Function |
|---|---|
| `services/feeds.py` (ingest) | `parse_feed(xml_or_url: str) -> ParsedFeed` and `sync_podcast(rss_url: str) -> Podcast` (create or refresh, upsert episodes) |
| `services/downloader.py` (ingest) | `download_episode(episode_id: int, on_progress: ProgressFn, force=False) -> Path` |
| `services/audio.py` (ingest) | `prepare_chunks(src: Path, workdir: Path, chunk_seconds: int, bitrate_kbps: int) -> list[AudioChunk(path, offset)]`, `cut_clip(src: Path, start: float, end: float, dst: Path) -> Path`, `probe_duration(path) -> float` |
| `services/transcribe.py` (ingest) | `transcribe_episode(episode_id: int, on_progress: ProgressFn, force=False) -> Transcript` |
| `services/indexing.py` (rag) | `index_episode(episode_id: int, on_progress: ProgressFn, force=False) -> int` (passages written), `remove_episode(episode_id: int) -> int`, `rebuild_index(on_progress: ProgressFn) -> int` |
| `services/summarize.py` (rag) | `summarize_episode(episode_id: int, on_progress: ProgressFn, force=False) -> Path`. After writing `summary.md` it calls `indexing.index_summary(episode_id)` |
| `services/vectorstore.py` (rag) | `get_vector_store() -> VectorStore`, cached. Chroma `PersistentClient(settings.chroma_dir)`, collection `"passages__" + slugify(settings.embedding_id)`, cosine space |
| `services/rag.py` (rag) | `answer_stream(req: ChatRequest) -> Iterator[ChatEvent]` (see SSE below) |
| `services/conversations.py` (rag) | CRUD helpers used by `api/conversations.py` and `rag.py` |
| `services/estimate.py` (ingest) | `estimate(sel: SelectionRequest) -> CostEstimate` |
| `jobs/worker.py` (ingest) | `worker = JobWorker()` with `async start()`, `async stop()`, `enqueue(job_id: int)`, `cancel(job_id: int)`. Also `create_jobs(sel: SelectionRequest) -> list[Job]` and `resolve_selection(session, sel) -> list[Episode]` |

`ProgressFn(fraction: float, message: str)` is defined in `app.domain`. The worker's implementation stores progress on the Job row, throttled to at most 1 write/second. It raises `JobCancelled` if the job was cancelled, so long steps stop promptly.

### Transcription pipeline (`services/transcribe.py`)
1. Download if needed. `audio.prepare_chunks` re-encodes to mono at `audio_bitrate_kbps` and splits into `audio_chunk_seconds` pieces. It cuts at silence when possible, and every piece is ≤ 24 MB. Each piece carries its offset.
2. Diarize chunk 1 with `known_speakers=[]`.
3. For each distinct speaker (≤ `max_known_speakers`), take its longest segment, clamped to 2–10 s, and `cut_clip` it into `work/ref_<label>.mp3`. Later chunks pass these as `known_speakers=[KnownSpeaker(name=label, reference_path)]`, so labels stay consistent. The OpenAI params are `known_speaker_names` and `known_speaker_references`, and the references are data URLs (`data:audio/mpeg;base64,...`).
4. Add the chunk offset to every segment. Merge consecutive segments with the same speaker when the gap is < 1.5 s.
5. **Speaker naming**: one `get_llm().complete(json_object=True)` call gets the podcast title, episode title/description and the first ~40 segments. It returns `{"A": "Andrew Huberman", "B": "Dr. Jane Doe"}`. If unknown, use `"Speaker A"`.
6. Write `transcript.json` + `transcript.md` via `storage.write_transcript`. Update `Episode.transcript_path/transcribed_at/speakers` and delete `work/`.

Backends (`providers/transcription/`):
- `openai_diarize`: `client.audio.transcriptions.create(model=diarize_model, file=..., response_format="diarized_json", chunking_strategy="auto", known_speaker_names=[...], known_speaker_references=[...])`, read from `resp.segments[*].{speaker,start,end,text}`. Skip items without `speaker`. `supports_diarization=True`.
- `openai_text_attrib`: `gpt-transcribe` returns plain text, then an LLM json_object call splits it into speaker turns `[{speaker,text}]`. Timestamps are interpolated by character position across the chunk duration. `supports_diarization=False`.
- `fake`: deterministic segments alternating "A"/"B", with lorem-like text that mentions the file name. No I/O besides reading the file size.

### Indexing (`services/indexing.py`)
- **Chunking**: walk the segments, accumulating text with prefix `"{speaker_name}: "`. A chunk runs to ~`chunk_chars` with `chunk_overlap_chars` of overlap. Prefer breaking at speaker turns. A chunk's metadata takes `speaker`/`start` from its first segment and `end` from its last. Mixed-speaker chunks keep the dominant speaker's name.
- **IDs**: `f"ep{episode_id}:{source}:{n}"`. Before upserting, `delete_episode`-style remove existing ids for that (episode, source), so re-indexing never duplicates.
- **Embeddings**: `get_embedder().embed` in batches. Update `Episode.indexed_at/passage_count`.

### RAG (`services/rag.py`)
1. Load or create the conversation (scope from the request; title = first 60 chars of the first message).
2. Condense: if there is prior history, call `complete()` to rewrite the user message as a standalone search query (last 6 messages). Otherwise use the message as-is.
3. Embed the query and `query(k=retrieval_k*2, where=scope_filter)`. Diversify to ≤ `max_passages_per_episode` per episode, then keep `retrieval_k`.
   - Scope filter: `{"episode_id": {"$in": ids}}` / `{"podcast_id": {"$in": ids}}`, combined with `$and`.
4. Prompt: a system message (answer only from the passages; cite as `[n]`; say so when the library does not cover the question), the numbered passages with episode/speaker/timestamp headers, the last 6 messages, and the user message.
5. Stream `get_llm().stream(...)`. Persist the user message before streaming and the assistant message (with the citations that are actually referenced, falling back to all of them) after.

## HTTP API (prefix `/api`; models in `app/schemas.py`)

| Method & path | Body / query | Response | Owner |
|---|---|---|---|
| GET `/health` | | `{"status":"ok"}` | integrator |
| GET `/config` | | `AppConfigOut` | integrator |
| GET `/podcasts` | | `PodcastOut[]` | ingest |
| POST `/podcasts` | `PodcastCreate` | `PodcastOut` (201; 409 if exists; 422 if not a feed) | ingest |
| POST `/podcasts/{id}/refresh` | | `PodcastOut` | ingest |
| DELETE `/podcasts/{id}` | `?delete_files=true` | 204. Removes episodes, vectors, files | ingest |
| GET `/episodes` | `podcast_id?, q?, search_description=false, status?, collected=false, limit=50, offset=0` | `EpisodeList`, newest first. `collected=true`: only episodes in the library (past "new", or with a queued/running job) | ingest |
| POST `/episodes/upload` | multipart `file`, `title?`, `show?` (default "My uploads"), `description?` | `EpisodeOut` (201), status "downloaded"; 422 if not audio, 413 over 2 GB. The show is a Podcast with `rss_url` `upload://<slug>` (refresh → 409); "delete data" keeps the uploaded audio | ingest |
| GET `/episodes/{id}` | | `EpisodeDetail` | ingest |
| POST `/episodes/{id}/check` | | `TranscriptCheck`: re-run the transcript health check | ingest |
| GET `/episodes/{id}/citations` | | `EpisodeCitationRef[]`: saved answers that cited this episode (transcript back-links) | ingest |
| GET `/episodes/{id}/audio` | | audio file (`FileResponse`, supports Range) | ingest |
| POST `/episodes/estimate` | `SelectionRequest` | `CostEstimate` | ingest |
| POST `/episodes/process` | `SelectionRequest` | `JobOut[]` (one job per episode needing work) | ingest |
| POST `/episodes/{id}/summarize` | `?force=false` | `JobOut` | ingest (calls rag's summarize via worker) |
| POST `/episodes/{id}/reindex` | | `JobOut` | ingest |
| DELETE `/episodes/{id}/data` | | 204. Deletes local files and vectors, resets state | ingest |
| GET `/jobs` | `status?` (comma list), `limit=100` | `JobOut[]`, newest first | ingest |
| GET `/jobs/{id}` | | `JobOut` | ingest |
| DELETE `/jobs/{id}` | | 204; 409 if queued/running (history only) | ingest |
| DELETE `/jobs` | `?status=done,failed,cancelled` | `{"deleted": n}` (finished jobs only) | ingest |
| GET `/discover/search` | `q, limit=20` | `DiscoverPodcast[]` via the Apple Podcasts directory (no key); 502 if unreachable | discover |
| GET `/discover/top` | `genre_id?, limit=24` | `DiscoverPodcast[]` top chart resolved to feed URLs (cached 1 h) | discover |
| GET `/discover/genres` | | `DiscoverGenre[]` | discover |
| GET `/podcasts/{id}/poster.png` | | the show's artwork as a 480px slate/marigold duotone (`services/artwork.py`, cached next to `artwork.img`); 404 without artwork | home |
| GET `/books/quote` | | `BookQuote` or null: a verified pull quote from a ready book, rotating daily (the home page's staff pick) | home |
| POST `/books/estimate` | `{episode_id}` | `BookEstimate` (chapters, target words, pages, USD, `voices`: speakers who can tell it, host first) | books |
| POST `/books` | `{episode_id, narrator?, tense="past"\|"present", form="retelling"\|"book"}` | `BookOut` (201); queues a `book` job; 409 without a transcript; 422 if `narrator` (a voice's label or name) is not a main named speaker. `tense` "present" tells the book as the conversation happens instead of looking back. `form` "book" (needs `narrator`) is the speaker's own non-fiction book, written to the reader; 422 without a narrator. Titles keep to the episode's own title | books |
| GET `/books`, GET `/books/{id}` | | `BookOut[]` / `BookOut` (status, live progress) | books |
| POST `/books/{id}/reshuffle` | | `BookOut`: new design seed, re-rendered, no model calls | books |
| GET `/books/{id}/pdf` | `?download=true` | the PDF (inline or attachment) | books |
| GET `/books/{id}/cover.png` | | cover thumbnail | books |
| DELETE `/books/{id}` | | 204; 409 while its job is active | books |
| POST `/jobs/{id}/cancel` | | `JobOut` | ingest |
| POST `/jobs/{id}/retry` | | `JobOut` (new job, same steps) | ingest |
| GET `/index/stats` | | `IndexStats` | rag |
| POST `/index/rebuild` | | `JobOut` (kind `rebuild_index`) | rag (enqueues via `worker`) |
| GET `/conversations` | | `ConversationOut[]`, recent first | rag |
| GET `/conversations/{id}` | | `ConversationDetail` | rag |
| PATCH `/conversations/{id}` | `ConversationPatch` | `ConversationOut` | rag |
| DELETE `/conversations/{id}` | | 204 | rag |
| POST `/chat` | `ChatRequest` | `text/event-stream` | rag |

Episode `status` is the furthest completed step: `indexed_at` → "indexed", `transcribed_at` → "transcribed", `downloaded_at` → "downloaded", otherwise "new".

### Chat SSE events (`POST /api/chat`, `sse-starlette` `EventSourceResponse`)
Each event has an `event:` name and JSON `data:`.

| event | data | when |
|---|---|---|
| `meta` | `{"conversation_id": 3, "user_message_id": 10, "query": "standalone query used"}` | first |
| `citations` | `{"citations": Citation[]}` | after retrieval, before tokens (all candidates, numbered) |
| `token` | `{"text": "partial"}` | many |
| `done` | `{"assistant_message_id": 11, "citations": Citation[]}` | last (citations actually used) |
| `error` | `{"detail": "..."}` | instead of `done` on failure |

The frontend reads the stream with `fetch` + `ReadableStream`, because EventSource cannot POST.

## Frontend routes
All pages share one indigo top bar (Pods wordmark, Chat / Library / Jobs, and a page slot on the right).
- `/`: Home, the library as a record shop. Wall: headline and library counts, duotone posters per show, the staff-pick quote, and a crate of sleeves (newest transcribed episodes as record-groove sleeves drawn from their segments, then sealed sleeves for untranscribed ones; arrow buttons/keys flip, divider tabs jump to a show). Counter: newest ready books (covers), the ask field (submits to `/chat?q=`), the last chat, and the running job if any.
- `/chat`, `/chat/:conversationId`: Chat. The Conversations menu sits in the top-bar slot; answers have the References column beside them. `?q=` sends a question on arrival. Old `/c/:id` links redirect.
- `/library`: "Your library" tab (feeds and the episode table, process with cost confirm) and a "Browse podcasts" tab (`?tab=browse`): name search and genre top charts from the Apple directory, one-click Add, RSS URL fallback.
- `/episodes/:id`: player, diarized transcript, cited-passage margin. `?t=` seeks and scrolls.
- `/books`: generated books as covers; Open / Download / Reshuffle design / Delete; live progress while writing. Episodes have a "Make a book" button (estimate, confirm, write).
- `/jobs`: live queue, Cancel / Retry / Delete per job, "Clear finished".

## Books (`app/books/`)
- `pipeline.py`: size (chapters ≈ minutes / 14, target ≈ 70% of spoken words) → one planning call over the whole numbered transcript (titles, chapters, sections mapped to segment ranges, glossary, quote picks) → sections written in parallel (`BOOK_PARALLELISM`), each from its own transcript slice with a word target proportional to it → quotes verified → `book.json` → render.
- `verify.py`: quotes are marked `⟦…⟧` by the writer and matched word for word (case/punctuation-insensitive) to a segment; attribution comes from that segment. Unverifiable inline quotes become plain narrative; unverifiable pull quotes are dropped.
- `theme.py`: a seed picks one of 8 colour families (contrast-guarded), 4 font pairs, cover art (tapes, rings, dots, waveform, mosaic, stripes, plain field, duotoned podcast artwork), cover layout, opener style and ornaments. `render.py` + `book.css` typeset with WeasyPrint; `art.py` / `tapes.py` draw the art from the conversation.
- Editor: after writing, one call reviews the narration against the full transcript (misattribution, factual slips, overstatement, repetition, housekeeping, off-topic). High/medium issues trigger one targeted rewrite of just those sections, re-verified; a rewrite that collapses the section is discarded. Results in `review.json` and on the book card.
- Voice: `Book.narrator` empty = a third-person narrator; a speaker's name = told in that speaker's first person. `speaker_roles` lists the main named speakers with a host guess (named in the podcast title, else most questions). `style(ctx)` / `quoting(ctx)` switch the writer and planner prompts; the editor also flags first-person material the speaker never voiced. The PDF's "How this book was made" note and colophon say the voice is AI-written, not by that person.
- Files: `data/podcasts/<podcast>/<episode>/books/<id>/{plan.json, book.json, review.json, book.pdf, cover.png}`.
- `scripts.repair_book <id>`: re-check and re-render an existing book with the current rules (no model calls).

## Transcript check (`services/transcript_check.py`)
Runs at the end of every transcription and on demand. Mechanical: gaps ≥ 45 s, transcript ending early, repeated-text loops, one voice holding > 95%, stray noise labels. One small model call confirms speaker names; a high-confidence swap is corrected in the transcript, anything less is reported. Never blocks; results live in `Episode.transcript_check` and show on the episode page.

## Measured spend (`app/spend.py`)
Every paid call (transcription chunks, chat completions, embeddings) passes the `usage` OpenAI returns to `spend.record`, which prices it (`PRICE_*`) on the current `Meter`. The worker opens a meter per job (`Job.cost_usd`); `transcribe_episode` opens a nested one for the transcription itself (`Episode.transcribe_cost`: USD, tokens per model, minutes). Thread pools submit through `spend.submit` so the meter follows. `services/estimate.transcription_rate` uses the measured USD/min of past transcriptions with the same model (≥ 5 min of them) instead of the configured price. A cancelled job's in-flight chunks finish after the job stops, so its recorded cost can be slightly low.

## Database migrations
`db.init_db` adds columns that models gained since a table was created (SQLite `ADD COLUMN`, existing rows keep their data and get the column default).

## Fake / demo mode
Set `LLM_PROVIDER=fake TRANSCRIBER=fake EMBEDDINGS_PROVIDER=fake DOWNLOAD_MODE=fake`.

`DOWNLOAD_MODE=fake` makes `download_episode` write a 1 KB placeholder `audio.mp3` instead of fetching. `uv run python -m scripts.seed_demo` creates a "Demo Podcast" with 3 episodes, writes realistic diarized `transcript.json` files, and indexes them with `FakeEmbedder`. All of it is offline and free.
