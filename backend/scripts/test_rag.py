"""RAG-specific test: forces queries that MUST hit ChromaDB and return sources."""
import requests
import json

BASE = "http://127.0.0.1:8000"
out = []

def log(msg):
    print(msg, flush=True)
    out.append(msg)

# Login
login = requests.post(f"{BASE}/api/auth/login",
                       data={"username": "jatin.faculty@tcet.com", "password": "secret123"})
token = login.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Fresh session
sess = requests.post(f"{BASE}/api/chat/sessions", headers=h, json={"title": "RAG Test"}).json()
sid = sess["session_id"]
log(f"Session: {sid}")

# ── TEST: RAG Query (should hit ChromaDB) ──────────────────────────
QUERIES = [
    "What do the uploaded notes say about backpropagation?",
    "Find information from my course material about neural networks",
    "what is segmentation on which page and document is it mentioned ?",
    "what are the different Page Replacement Algorithms section 7 page 57 onwards?"
]

for i, query in enumerate(QUERIES, 1):
    log(f"\n=== RAG TEST {i}: {query} ===")
    resp = requests.post(f"{BASE}/api/chat/sessions/{sid}/message", headers=h,
                         json={"query": query}, stream=True)

    events = []
    tokens = []
    for line in resp.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            ev = json.loads(line[6:])
            events.append(ev)
            if ev["t"] == "token":
                tokens.append(ev["d"])

    # Print non-token events
    for ev in events:
        if ev["t"] != "token":
            log(f'  [{ev["t"].upper():8s}] {json.dumps(ev["d"], default=str)[:150]}')

    # Check if "Searching knowledge base" status appeared (= RAG path taken)
    statuses = [ev["d"] for ev in events if ev["t"] == "status"]
    rag_hit = any("Searching" in s or "knowledge" in s.lower() for s in statuses)
    log(f"  [RAG HIT] {'YES - retriever_vector_node was called' if rag_hit else 'NO - went conversational!'}")

    # Check sources
    source_events = [ev for ev in events if ev["t"] == "sources"]
    if source_events:
        sources = source_events[0]["d"]
        log(f"  [SOURCES] {len(sources)} source(s) returned")
        for s in sources[:5]:
            fn = s.get("file_name", "?")
            pg = s.get("page_number", "?")
            sc = s.get("relevance_score", "?")
            ft = s.get("file_type", "?")
            log(f"     -> {fn}  page={pg}  type={ft}  score={sc}")
    else:
        log("  [SOURCES] NONE returned!")

    full = "".join(tokens)
    log(f"  [RESPONSE] {len(tokens)} chunks, {len(full)} chars")
    # Check if response cites sources
    has_citation = any(x in full.lower() for x in ["page", "module", "according to", "source", "notes"])
    log(f"  [CITES?]  {'YES' if has_citation else 'NO'}")
    log(f"  [PREVIEW] {full[:250]}...")

# Final DB check
hist = requests.get(f"{BASE}/api/chat/sessions/{sid}/history", headers=h).json()
log(f"\n=== DB: {hist['count']} messages saved ===")
for m in hist["messages"]:
    role = m["role"]
    extra = ""
    if m.get("sources"):
        extra = f" [+{len(m['sources'])} sources]"
    if m.get("intent"):
        extra += f" intent={m['intent']}"
    log(f"  [{role}] {m['content'][:80]}...{extra}")

log("\n=== RAG TEST COMPLETE ===")

with open("scripts/test_rag_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
