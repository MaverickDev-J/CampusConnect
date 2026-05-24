"""
ChromaDB Inspector — View all processed chunks, metadata, and stats.

Usage:
    cd backend
    uv run python scripts/inspect_chroma.py                     # full summary
    uv run python scripts/inspect_chroma.py --file_id <ID>      # chunks for one file
    uv run python scripts/inspect_chroma.py --peek 5            # show first N chunks
    uv run python scripts/inspect_chroma.py --search "neural"   # text search
    uv run python scripts/inspect_chroma.py --stats             # metadata breakdown
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import chromadb

CHROMA_PATH = str(Path(__file__).resolve().parent.parent / "chroma_data")
COLLECTION_NAME = "campus_vectors"

# ── Colours (ANSI) ──────────────────────────────────────────────────
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        print(f"{YELLOW}Collection '{COLLECTION_NAME}' not found in {CHROMA_PATH}{RESET}")
        print("Have you uploaded and processed a file yet?")
        sys.exit(1)


def print_chunk(idx: int, chunk_id: str, meta: dict, doc: str, show_text: bool = True):
    """Pretty-print a single chunk."""
    print(f"\n{BOLD}{CYAN}─── Chunk {idx} ───{RESET}")
    print(f"  {BOLD}ID:{RESET}         {chunk_id}")
    print(f"  {BOLD}File:{RESET}       {meta.get('file_name', '?')} ({meta.get('file_type', '?')})")
    print(f"  {BOLD}Page:{RESET}       {meta.get('page_number', '?')}  |  {BOLD}Chunk:{RESET} {meta.get('chunk_index', '?')}")
    print(f"  {BOLD}Year:{RESET}       {meta.get('year', '?')}  |  {BOLD}Branch:{RESET} {meta.get('branch', '?')}")
    print(f"  {BOLD}Subject:{RESET}    {meta.get('subject', '?')}")
    print(f"  {BOLD}Doc Type:{RESET}   {meta.get('doc_type', '?')}")
    unit = meta.get("unit")
    if unit is not None:
        print(f"  {BOLD}Unit:{RESET}       {unit}")
    print(f"  {BOLD}Visibility:{RESET} {meta.get('visibility', '?')}")
    print(f"  {BOLD}Uploaded By:{RESET} {meta.get('uploaded_by', '?')}")
    if show_text:
        wrapped = textwrap.fill(doc, width=90, initial_indent="    ", subsequent_indent="    ")
        print(f"  {BOLD}Text:{RESET}\n{DIM}{wrapped}{RESET}")


# ── Commands ────────────────────────────────────────────────────────

def cmd_summary(col: chromadb.Collection):
    """Show a high-level summary of everything in ChromaDB."""
    total = col.count()
    print(f"\n{BOLD}{GREEN}╔══════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{GREEN}║   ChromaDB Inspector — Summary       ║{RESET}")
    print(f"{BOLD}{GREEN}╚══════════════════════════════════════╝{RESET}")
    print(f"\n  Collection:  {BOLD}{COLLECTION_NAME}{RESET}")
    print(f"  Path:        {CHROMA_PATH}")
    print(f"  Total chunks: {BOLD}{total}{RESET}")

    if total == 0:
        print(f"\n  {YELLOW}No chunks found. Upload and process a file first.{RESET}\n")
        return

    # Get all metadata for stats
    all_data = col.get(include=["metadatas"])
    metadatas = all_data["metadatas"]

    # Group by file
    files: dict[str, dict] = {}
    for m in metadatas:
        fid = m.get("file_id", "unknown")
        if fid not in files:
            files[fid] = {
                "name": m.get("file_name", "?"),
                "type": m.get("file_type", "?"),
                "year": m.get("year", "?"),
                "branch": m.get("branch", "?"),
                "subject": m.get("subject", "?"),
                "doc_type": m.get("doc_type", "?"),
                "chunks": 0,
                "pages": set(),
            }
        files[fid]["chunks"] += 1
        files[fid]["pages"].add(m.get("page_number", 0))

    print(f"  Unique files: {BOLD}{len(files)}{RESET}\n")

    print(f"  {BOLD}{'File ID':<45} {'Name':<25} {'Type':<6} {'Chunks':<8} {'Pages':<6} {'Year':<5} {'Branch':<8} {'Subject'}{RESET}")
    print(f"  {'─'*140}")
    for fid, info in files.items():
        fid_short = fid[:42] + "..." if len(fid) > 45 else fid
        name_short = info['name'][:22] + "..." if len(info['name']) > 25 else info['name']
        print(
            f"  {fid_short:<45} {name_short:<25} {info['type']:<6} "
            f"{info['chunks']:<8} {len(info['pages']):<6} "
            f"{str(info['year']):<5} {info['branch']:<8} {info['subject']}"
        )
    print()


def cmd_peek(col: chromadb.Collection, n: int):
    """Show the first N chunks with full details."""
    result = col.peek(limit=n)
    ids = result["ids"]
    metadatas = result["metadatas"]
    documents = result["documents"]

    print(f"\n{BOLD}Showing first {len(ids)} chunks:{RESET}")
    for i, (cid, meta, doc) in enumerate(zip(ids, metadatas, documents), 1):
        print_chunk(i, cid, meta, doc)
    print()


def cmd_file(col: chromadb.Collection, file_id: str):
    """Show all chunks for a specific file_id."""
    result = col.get(
        where={"file_id": file_id},
        include=["metadatas", "documents"],
    )
    ids = result["ids"]
    if not ids:
        print(f"\n{YELLOW}No chunks found for file_id={file_id}{RESET}\n")
        return

    metadatas = result["metadatas"]
    documents = result["documents"]

    # Sort by page_number, chunk_index
    sorted_data = sorted(
        zip(ids, metadatas, documents),
        key=lambda x: (x[1].get("page_number", 0), x[1].get("chunk_index", 0)),
    )

    file_name = metadatas[0].get("file_name", "unknown")
    print(f"\n{BOLD}{GREEN}File: {file_name}{RESET}")
    print(f"  file_id: {file_id}")
    print(f"  Total chunks: {len(ids)}")

    for i, (cid, meta, doc) in enumerate(sorted_data, 1):
        print_chunk(i, cid, meta, doc)
    print()


def cmd_search(col: chromadb.Collection, query: str):
    """Search chunks by text content (uses ChromaDB's built-in where_document)."""
    result = col.get(
        where_document={"$contains": query},
        include=["metadatas", "documents"],
    )
    ids = result["ids"]
    if not ids:
        print(f"\n{YELLOW}No chunks contain '{query}'{RESET}\n")
        return

    print(f"\n{BOLD}Found {len(ids)} chunks containing '{query}':{RESET}")
    for i, (cid, meta, doc) in enumerate(zip(ids, result["metadatas"], result["documents"]), 1):
        print_chunk(i, cid, meta, doc, show_text=True)
    print()


def cmd_stats(col: chromadb.Collection):
    """Show metadata breakdown (unique values per field)."""
    all_data = col.get(include=["metadatas"])
    metadatas = all_data["metadatas"]
    total = len(metadatas)

    if total == 0:
        print(f"\n{YELLOW}No chunks to analyze.{RESET}\n")
        return

    print(f"\n{BOLD}{GREEN}╔══════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{GREEN}║   Metadata Breakdown                 ║{RESET}")
    print(f"{BOLD}{GREEN}╚══════════════════════════════════════╝{RESET}")

    fields = ["year", "branch", "subject", "doc_type", "file_type", "visibility", "uploaded_by"]
    for field in fields:
        values: dict[str, int] = {}
        for m in metadatas:
            val = str(m.get(field, "—"))
            values[val] = values.get(val, 0) + 1

        print(f"\n  {BOLD}{field}:{RESET}")
        for val, count in sorted(values.items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 50)
            print(f"    {val:<30} {count:>5} chunks  {DIM}{bar}{RESET}")

    print()


def cmd_export_json(col: chromadb.Collection):
    """Export all chunks as JSON to stdout."""
    all_data = col.get(include=["metadatas", "documents"])
    records = []
    for cid, meta, doc in zip(all_data["ids"], all_data["metadatas"], all_data["documents"]):
        records.append({"id": cid, "metadata": meta, "text": doc})
    print(json.dumps(records, indent=2, ensure_ascii=False))


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inspect ChromaDB campus_vectors collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file_id", type=str, help="Show all chunks for a specific file_id")
    parser.add_argument("--peek", type=int, metavar="N", help="Show first N chunks with full text")
    parser.add_argument("--search", type=str, help="Text search (substring match in documents)")
    parser.add_argument("--stats", action="store_true", help="Show metadata breakdown")
    parser.add_argument("--export", action="store_true", help="Export all chunks as JSON")

    args = parser.parse_args()
    col = get_collection()

    if args.file_id:
        cmd_file(col, args.file_id)
    elif args.peek:
        cmd_peek(col, args.peek)
    elif args.search:
        cmd_search(col, args.search)
    elif args.stats:
        cmd_stats(col)
    elif args.export:
        cmd_export_json(col)
    else:
        cmd_summary(col)


if __name__ == "__main__":
    main()
