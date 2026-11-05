# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React + Vite + TypeScript frontend (npm), served by nginx; FastAPI backend (Python 3.12, uv); SQLite + Chroma for local persistence; Docker Compose for local deployment. Chosen by the user during planning.

## Users
One person — the owner — using it as a personal research tool on their own machine. They build a library of podcast episodes once, then come back repeatedly to ask questions across everything they've collected. Screenshots of the site may also be shown as a portfolio demo of the owner's engineering work, so the interface must hold up when seen out of context by reviewers.

## Product Purpose
A local RAG chatbot over podcast episodes. The owner picks episodes from any RSS feed (Huberman Lab preloaded), the app downloads, transcribes with per-speaker diarization and indexes them into a persistent local knowledge base, and the chatbot answers questions grounded in those transcripts. Success: open the site and get a trustworthy, cited answer within seconds from a library built weeks ago — no reprocessing.

## Positioning
Answers come from the owner's own locally stored, speaker-attributed transcripts and every answer cites the episode, who said it, and when — one click jumps to that moment in the audio.

## Operating Context
- Two loops: an occasional *build* loop (Library: browse feeds, search episodes, select many, confirm cost, process) and a frequent *use* loop (Chat over the whole library or a scoped subset).
- Processing is slow (minutes per episode) and runs as a background job queue with visible progress.
- Everything lives in a local `./data` folder: audio, transcripts, summaries, vector index, chat history.

## Capabilities and Constraints
- Any RSS podcast feed; Huberman Lab (`https://feeds.megaphone.fm/hubermanlab`) is the default suggestion.
- Transcription: OpenAI diarization model (speaker-labelled segments with timestamps); pluggable fallback. Embeddings: OpenAI. Chat and summaries: `gpt-6-luna` via OpenAI or OpenRouter.
- Processing costs real money: the UI must show an estimated cost and require explicit confirmation before any paid step. Nothing paid happens implicitly.
- Summaries are optional and generated per episode on demand.
- A fake/demo mode exists for offline, free use.
- Terminology: "Library" (what has been collected), "Episode", "Passage" (indexed chunk), "Scope" (what the chat searches), "Job".

## Brand Commitments
None established. The app is not affiliated with Huberman Lab or any podcast; it must not use podcast logos or branding as its own identity.

## Evidence on Hand
- `example_of_usage.png` — screenshot of the old Gradio chatbot (anti-reference for the new UI, not a brand asset).
- No real transcripts, testimonials or metrics exist yet; demo content must be clearly fictional and never attribute invented quotes to real people.

## Product Principles
1. The chatbot is the product; the Library exists to feed it.
2. Every answer is traceable — citation to episode, speaker, timestamp.
3. Money is spent only on explicit, informed confirmation.
4. Build once, reuse forever — persistent, incremental, never redo finished work.
5. Honest states — show what is indexed, what is processing, and what failed.

## Accessibility & Inclusion
No product-specific requirement established; target WCAG 2.2 AA as the baseline.
