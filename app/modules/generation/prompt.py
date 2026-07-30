"""Grounded generation prompt: numbered context + strict citation rules."""
from __future__ import annotations

from collections.abc import Sequence

from app.modules.retrieval.dense import RetrievedChunk

SYSTEM_PROMPT = """You are a technical documentation assistant for FastAPI.
Answer the user's question using ONLY the numbered context below.

Rules:
1. Cite sources inline as [1], [2], ... using the numbers of the context blocks you rely on.
2. Only cite blocks you actually used, and list them in `citations_used`.
3. If the context does not contain enough information, set `has_sufficient_context` to false
   and say you don't have enough information — do NOT guess.
4. Preserve exact code, identifiers, and symbols from the context.
5. Do not use outside knowledge. Be concise.
6. Set `self_confidence` (0-1) to how sure you are the answer is correct and fully grounded
   in the context — be honest and use a low value if the context was thin or you had to stretch."""


# Names a chat from its opening question. The examples are the contract: a topic
# noun-phrase, never the question echoed back — that is what made titles look like
# duplicated prompts in the sidebar.
TITLE_SYSTEM_PROMPT = """You name a chat conversation from the user's first message.

Rules:
1. Return a short noun phrase naming the TOPIC — not the question itself.
2. At most {max_words} significant words (of/in/a/the don't count). Title Case.
   No quotes, no trailing punctuation.
3. Never open with How/What/Why/Can/Should/Explain. Drop filler like "explain me about",
   "I want to", "help me understand", "tell me" and keep the subject.
4. Turn a problem or a goal into an action: "Fixing ...", "Improving ...", "Building ...",
   "Setting Up ...", "Understanding ...".
5. Keep proper nouns, product names and acronyms exactly as written (FastAPI, BM25, LangGraph).
6. Use the language of the message.

Examples:
"What is RAG?" -> Understanding RAG
"How do I install FastAPI on Windows?" -> FastAPI Setup on Windows
"Why am I getting ModuleNotFoundError in LangChain?" -> Fixing LangChain Import Errors
"I want to build a chatbot using LangGraph and Ollama." -> Building a LangGraph Chatbot
"My FAISS retriever isn't returning relevant documents." -> Improving FAISS Retrieval
"What is the difference between BM25 and vector search?" -> BM25 vs Vector Search
"Help me understand how metadata is used during RAG retrieval." -> Metadata in RAG Retrieval
"explain me about "Aetio-pathology of diabetes"" -> Aetio-Pathology of Diabetes"""


def build_title_prompt(max_words: int) -> str:
    return TITLE_SYSTEM_PROMPT.format(max_words=max_words)


def _locator(c: RetrievedChunk) -> str:
    """Human-readable provenance suffix: page, section, and/or structured locator."""
    parts: list[str] = []
    if c.page_number is not None:
        parts.append(f"p.{c.page_number}")
    if c.section_path:
        parts.append(f"Section: {c.section_path}")
    if c.locator:  # structured formats: "rows 21-40" / "$.items[3]" / "/catalog/book[2]"
        parts.append(c.locator)
    return f" ({', '.join(parts)})" if parts else ""


def build_context(chunks: Sequence[RetrievedChunk]) -> str:
    blocks = [
        f'[{i}] From "{c.source}"{_locator(c)}\n{c.text}'
        for i, c in enumerate(chunks, start=1)
    ]
    return "\n\n".join(blocks)


def build_user_prompt(query: str, chunks: Sequence[RetrievedChunk]) -> str:
    return f"Question: {query}\n\nContext:\n{build_context(chunks)}"
