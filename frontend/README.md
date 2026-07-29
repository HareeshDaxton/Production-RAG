# Production RAG — Chat UI

ChatGPT-style interface for the Production RAG API. Next.js 15 + TypeScript + Tailwind v4.

## Run

```bash
cd frontend
npm install
copy .env.local.example .env.local   # macOS/Linux: cp
npm run dev                          # http://localhost:3000
```

Backend in a second terminal from the repo root:

```bash
uv run uvicorn app.main:app --reload
```

## Features

| Feature | Notes |
| --- | --- |
| Chat interface | Single page, ChatGPT layout: sidebar + thread + composer |
| **Streaming responses** | Real token-by-token over SSE (`POST /v1/ask/stream`) |
| File upload | PDF, DOCX, MD, HTML, TXT, CSV, JSON, XML, images (OCR) |
| Conversation history | Sidebar; stored in `localStorage` (last 50) |
| Source citations | Document name, **page**, section, locator + judge verdict |
| Loading indicator | Typing dots before first token, caret while streaming |
| Copy / Regenerate | Regenerate replays the same question in place |
| Thumbs up / down | `POST /v1/feedback` → Phase 6 auto-eval candidates |
| Clear chat / New chat | Both, plus per-conversation delete |

## How streaming works

`POST /v1/ask/stream` emits SSE frames:

- `meta` — retrieval mode and chunk count
- `delta` — a slice of new answer text (many)
- `final` — the **verified** response: citations, confidence, and the IDK gate applied

The streamed text is a draft. Citations and confidence can only be computed once
generation finishes, so `final` is authoritative and replaces what was streamed. When
the quality gate swaps in a refusal, `final.replaced` is true and the UI says so
explicitly rather than silently changing the text.

## Contract

`lib/types.ts` mirrors `app/models/schemas.py`. **If you change a Pydantic schema,
update `lib/types.ts`.**
