"""Fetch the real corpus: FastAPI docs (markdown) + GitHub issues.

Populates `data/corpus/` (the default ingest source) with two subtrees:

    data/corpus/docs/     <- FastAPI docs markdown  (docs/en/docs/**/*.md)
    data/corpus/issues/   <- one markdown file per GitHub issue

Both are plain markdown with YAML front-matter, so the existing loader/chunker
ingest them unchanged (`POST /v1/ingest` with no body, or
`uv run python -m scripts.fetch_corpus` then `uv run python -m scripts.fetch_corpus --stats`).

GitHub's unauthenticated API allows ~60 requests/hour; set `GITHUB_TOKEN` in the
environment (or `--token`) for 5000/hour — needed if you pull many issues.

Usage:
    uv run python scripts/fetch_corpus.py                 # docs + issues (default caps)
    uv run python scripts/fetch_corpus.py --docs-only
    uv run python scripts/fetch_corpus.py --issues-only --max-issues 300
    uv run python scripts/fetch_corpus.py --repo tiangolo/fastapi --ref master
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "corpus"

DEFAULT_REPO = "fastapi/fastapi"
DEFAULT_REF = "master"
DOCS_PREFIX = "docs/en/docs/"  # English docs live here in the FastAPI repo

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def _client(token: str | None) -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "production-rag-fetch"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)


def _yaml_escape(value: str) -> str:
    """Quote a scalar for a YAML front-matter value."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --- docs -------------------------------------------------------------------


def fetch_docs(client: httpx.Client, repo: str, ref: str, out: Path) -> int:
    """Download every markdown file under the repo's English docs tree."""
    tree_url = f"{API}/repos/{repo}/git/trees/{ref}?recursive=1"
    resp = client.get(tree_url)
    resp.raise_for_status()
    tree = resp.json().get("tree", [])
    md_paths = [
        item["path"]
        for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith(DOCS_PREFIX)
        and item["path"].endswith(".md")
    ]
    print(f"docs: found {len(md_paths)} markdown files under {DOCS_PREFIX}")

    docs_out = out / "docs"
    count = 0
    for path in md_paths:
        raw = client.get(f"{RAW}/{repo}/{ref}/{path}")
        if raw.status_code != 200:
            print(f"  skip {path} (HTTP {raw.status_code})", file=sys.stderr)
            continue
        rel = path[len(DOCS_PREFIX):]  # keep the docs subtree structure
        dest = docs_out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(raw.text, encoding="utf-8")
        count += 1
        if count % 50 == 0:
            print(f"  ...{count} files")
    print(f"docs: wrote {count} files to {docs_out}")
    return count


# --- issues -----------------------------------------------------------------


def _issue_to_markdown(issue: dict) -> str:
    number = issue["number"]
    title = issue.get("title") or f"Issue {number}"
    state = issue.get("state", "")
    labels = [lbl["name"] for lbl in issue.get("labels", []) if isinstance(lbl, dict)]
    user = (issue.get("user") or {}).get("login", "")
    body = (issue.get("body") or "").strip() or "_(no description)_"

    front = [
        "---",
        f"title: {_yaml_escape(title)}",
        f"issue_number: {number}",
        f"state: {state}",
        f"author: {user}",
        f"url: {issue.get('html_url', '')}",
    ]
    if labels:
        front.append("labels: [" + ", ".join(_yaml_escape(x) for x in labels) + "]")
    front.append("---")

    header = f"# {title}\n\n> Issue #{number} · {state}"
    if labels:
        header += " · " + ", ".join(labels)
    return "\n".join(front) + "\n\n" + header + "\n\n" + body + "\n"


def fetch_issues(
    client: httpx.Client, repo: str, out: Path, max_issues: int, state: str
) -> int:
    """Download issues (excluding pull requests) as one markdown file each."""
    issues_out = out / "issues"
    issues_out.mkdir(parents=True, exist_ok=True)

    count = 0
    page = 1
    per_page = 100
    while count < max_issues:
        resp = client.get(
            f"{API}/repos/{repo}/issues",
            params={"state": state, "per_page": per_page, "page": page},
        )
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
            wait = max(0, reset - int(time.time())) + 1
            print(f"  rate-limited; sleeping {wait}s (set GITHUB_TOKEN to avoid)", file=sys.stderr)
            time.sleep(min(wait, 60))
            continue
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for issue in batch:
            if "pull_request" in issue:  # the issues API also returns PRs; skip them
                continue
            if count >= max_issues:
                break
            dest = issues_out / f"issue-{issue['number']}.md"
            dest.write_text(_issue_to_markdown(issue), encoding="utf-8")
            count += 1
        print(f"  issues page {page}: total written {count}")
        page += 1

    print(f"issues: wrote {count} files to {issues_out}")
    return count


# --- stats / cli ------------------------------------------------------------


def show_stats(out: Path) -> None:
    docs = list((out / "docs").rglob("*.md")) if (out / "docs").exists() else []
    issues = list((out / "issues").glob("*.md")) if (out / "issues").exists() else []
    print(f"corpus at {out}")
    print(f"  docs   : {len(docs)} markdown files")
    print(f"  issues : {len(issues)} markdown files")
    print(f"  total  : {len(docs) + len(issues)} files")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch FastAPI docs + GitHub issues corpus.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name (default fastapi/fastapi)")
    parser.add_argument("--ref", default=DEFAULT_REF, help="git ref/branch (default master)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output corpus dir")
    parser.add_argument("--docs-only", action="store_true", help="fetch docs only")
    parser.add_argument("--issues-only", action="store_true", help="fetch issues only")
    parser.add_argument("--max-issues", type=int, default=200, help="cap issues (default 200)")
    parser.add_argument(
        "--issue-state", default="all", choices=["all", "open", "closed"], help="issue state"
    )
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"), help="GitHub token")
    parser.add_argument("--stats", action="store_true", help="just print corpus counts and exit")
    args = parser.parse_args()

    if args.stats:
        show_stats(args.out)
        return 0

    do_docs = not args.issues_only
    do_issues = not args.docs_only
    args.out.mkdir(parents=True, exist_ok=True)

    try:
        with _client(args.token) as client:
            if do_docs:
                fetch_docs(client, args.repo, args.ref, args.out)
            if do_issues:
                fetch_issues(client, args.repo, args.out, args.max_issues, args.issue_state)
    except httpx.HTTPError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    show_stats(args.out)
    print("\nNext: uv run uvicorn app.main:app --reload  then  POST /v1/ingest {}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
