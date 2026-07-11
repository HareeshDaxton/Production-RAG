"""External-resource clients (models, vector store, sqlite, LLM).

Each client is a thin, lazily-initialised boundary so it can later be swapped
(e.g. SQLite -> Postgres) or moved into a separate service without touching callers.
"""
