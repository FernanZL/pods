# Pods: podcast library chat

A local RAG chatbot over podcast episodes. Pick episodes from any RSS feed; Huberman Lab is the suggested default. The app downloads them, transcribes them **with per-speaker diarization**, and indexes them into a persistent local vector store. Then you chat with the whole library, and every answer cites the episode, who said it, and when.

**Build once, chat forever.** Everything is saved under `./data`: audio, transcripts, summaries, the Chroma index and chat history. Next time you open the site, the chatbot is ready immediately. Add more episodes whenever you like and they extend the same index.

![old Gradio prototype](example_of_usage.png)
*(The original notebook prototype. The new UI replaces it.)*

## Architecture

```
browser ── nginx (frontend :8080) ──/api──▶ FastAPI (backend :8000)
                                            ├─ SQLite  data/app.db        podcasts, episodes, jobs, chats
                                            ├─ Chroma  data/chroma/        passage embeddings
                                            ├─ files   data/podcasts/…     audio, transcript.json/.md, summary.md
                                            └─ job worker  download → transcribe → index (+ summarize)
```

| Concern | Choice |
|---|---|
| Backend | FastAPI, SQLModel/SQLite, ChromaDB, Python 3.12, managed with **uv** |
| Frontend | React + Vite + TypeScript, managed with **npm**, served by nginx |
| Transcription | OpenAI `gpt-4o-transcribe-diarize` (speaker-labelled segments), with fallback `gpt-transcribe` + LLM speaker attribution |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat + summaries | `gpt-6-luna` via **OpenAI or OpenRouter** (`LLM_PROVIDER`) |

There's no Hugging Face, no local models and no GPU. Contracts and module ownership are in [`docs/architecture.md`](docs/architecture.md). The original notebooks are kept in [`notebooks/legacy/`](notebooks/legacy).

## Quick start (Docker)

```bash
cp .env.example .env        # add OPENAI_API_KEY (and OPENROUTER_API_KEY if you use it)
docker compose up --build   # add -d to run in the background
open http://localhost:8080
```

1. **Library**: click *Add Huberman Lab* (or paste any RSS URL).
2. Search (e.g. `essentials`), select episodes (or *Select all matching*), then click *Process*.
3. A confirmation dialog shows the episode count, minutes and **estimated cost**. Nothing paid runs before you confirm.
4. Follow progress in **Jobs**. Each episode becomes chat-ready as soon as it is indexed.
5. **Chat**: ask anything. Narrow the scope to one podcast or chosen episodes. Click a citation to jump to that moment in the episode.

`./data` is a bind mount, so it survives `docker compose down` and rebuilds. The backend runs as whoever owns `./data` on the host, so those files stay yours.

## Local development

```bash
./dev install      # uv sync + npm install
./dev backend      # API on :8000 (reload), data in ./data
./dev frontend     # Vite on :5173, proxies /api to :8000
./dev test         # offline backend tests + frontend build
./dev lint
```

### Free demo mode (no keys, no network, no cost)

```bash
./dev seed-demo    # writes a fictional "Demo Podcast" with diarized transcripts to ./data-demo
./dev demo         # API in fake mode against ./data-demo
./dev frontend     # then open http://localhost:5173
```

Fake mode (`LLM_PROVIDER=fake TRANSCRIBER=fake EMBEDDINGS_PROVIDER=fake DOWNLOAD_MODE=fake`) swaps every paid provider for a deterministic local stand-in. The test suite always runs this way.

## Books

Any transcribed episode can become a long-form PDF book: open the episode and choose **Make a book**. Pods plans chapters from the whole conversation, writes each section from its own stretch of the transcript (a 2-hour episode becomes roughly 8–10 chapters and 15–20k words), checks every quote word for word against the recording, and typesets it with its own design: one of 8 colour families, 4 font pairings and 8 kinds of cover art, several drawn from the conversation itself. Before you see it, an editor pass checks the narration against the transcript (who said what, numbers, overstatement, repetition) and rewrites only the sections it flags. **Reshuffle design** in Books gives the same text a new look for free.

Every transcription also gets an automatic check (gaps, repeated text, speaker problems, and a quick confirmation of the speaker names), shown on the episode page. Writing a book with `gpt-6-luna` costs a few cents.

## Costs and models

- Transcription is the main cost: roughly duration × per-minute price. Prices live in `.env` / `app/config.py` (`PRICE_*`). Check them against current OpenAI pricing.
- Embeddings and chat are cheap in comparison. Summaries are optional and generated per episode on demand.
- Finished steps are never redone: re-processing skips anything already downloaded, transcribed or indexed. *Rebuild index* re-embeds from the transcripts on disk and never re-transcribes.
- **Model sunset:** OpenAI shuts down `gpt-4o-transcribe-diarize` on **2027-02-26**. Before then, switch to `TRANSCRIBER=openai_text` (`gpt-transcribe`, with an LLM inferring speaker turns), or to a newer diarizing model through `DIARIZE_MODEL`.

## How diarization stays consistent

Episodes are re-encoded and split into ~10-minute chunks, since the API limit is 25 MB per file. Chunk 1 is diarized on its own. Then a 2–10 s reference clip is cut for each detected voice and passed to every later chunk as `known_speaker_references`, so the same person keeps the same label across the whole episode. A single LLM call maps the labels to names using the episode title and description.
