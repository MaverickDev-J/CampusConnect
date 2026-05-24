"""
Quick demo: Run a single query through the LangGraph chat pipeline.
Usage: uv run python scripts/run_chat_demo.py "what is segmentation"
"""
import sys, requests, json

BASE = "http://127.0.0.1:8000"
QUERY = sys.argv[1] if len(sys.argv) > 1 else "what is segmentation"

# ── Step 1: Login ────────────────────────────────────────────────
print("🔐 Logging in...")
r = requests.post(f"{BASE}/api/auth/login",
                   data={"username": "jatin.faculty@tcet.com", "password": "secret123"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ── Step 2: Create session ───────────────────────────────────────
print("📋 Creating chat session...")
sess = requests.post(f"{BASE}/api/chat/sessions", headers=h,
                     json={"title": "Quick Demo"}).json()
sid = sess["session_id"]
print(f"   Session ID: {sid}")

# ── Step 3: Send query via SSE ───────────────────────────────────
print(f"\n💬 Sending: \"{QUERY}\"\n")
print("─" * 60)

resp = requests.post(f"{BASE}/api/chat/sessions/{sid}/message",
                     headers=h, json={"query": QUERY}, stream=True)

full_text = []
sources = []

for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    ev = json.loads(line[6:])
    t, d = ev["t"], ev["d"]

    if t == "status":
        print(f"  ⏳ {d}")
    elif t == "token":
        print(d, end="", flush=True)
        full_text.append(d)
    elif t == "sources":
        sources = d
    elif t == "done":
        pass

print("\n" + "─" * 60)

# ── Step 4: Show sources ─────────────────────────────────────────
if sources:
    print(f"\n📚 Sources ({len(sources)} chunks retrieved from ChromaDB):")
    for s in sources[:5]:
        fn = s.get("file_name", "?")
        pg = s.get("page_number", "?")
        sc = s.get("relevance_score", 0)
        print(f"   📄 {fn}  →  Page {pg}  (score: {sc:.2f})")
else:
    print("\n📚 No sources (conversational/out-of-scope query)")

print("\n✅ Done!")
