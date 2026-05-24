"""Clean e2e test for SSE chat — writes results to a file for clear reading."""
import requests
import json
import sys

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

# Create a FRESH session for clean test
sess = requests.post(f"{BASE}/api/chat/sessions", headers=h, json={"title": "E2E Test"}).json()
sid = sess["session_id"]
log(f"Session: {sid}")

# ── TEST 1: RAG Query ──────────────────────────────────────────────
log("\n=== TEST 1: RAG Query ===")
resp = requests.post(f"{BASE}/api/chat/sessions/{sid}/message", headers=h,
                     json={"query": "what are the different Page Replacement Algorithms section 7 page 57 onwards?"}, stream=True)

events = []
tokens = []
for line in resp.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        ev = json.loads(line[6:])
        events.append(ev)
        if ev["t"] == "token":
            tokens.append(ev["d"])

for ev in events:
    if ev["t"] != "token":
        log(f'  [{ev["t"].upper():8s}] {json.dumps(ev["d"])[:120]}')

full = "".join(tokens)
log(f"  [TOKENS]  {len(tokens)} chunks, {len(full)} chars")
log(f"  [PREVIEW] {full[:200]}...")

# Verify persistence
hist = requests.get(f"{BASE}/api/chat/sessions/{sid}/history", headers=h).json()
log(f"  [DB]      {hist['count']} messages saved")
for m in hist["messages"]:
    log(f"            [{m['role']}] {m['content'][:80]}...")

# ── TEST 2: Conversational Query ──────────────────────────────────
log("\n=== TEST 2: Conversational Query ===")
resp2 = requests.post(f"{BASE}/api/chat/sessions/{sid}/message", headers=h,
                      json={"query": "Thanks! Can you explain that more simply?"}, stream=True)

events2 = []
tokens2 = []
for line in resp2.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        ev = json.loads(line[6:])
        events2.append(ev)
        if ev["t"] == "token":
            tokens2.append(ev["d"])

for ev in events2:
    if ev["t"] != "token":
        log(f'  [{ev["t"].upper():8s}] {json.dumps(ev["d"])[:120]}')

full2 = "".join(tokens2)
log(f"  [TOKENS]  {len(tokens2)} chunks, {len(full2)} chars")
log(f"  [PREVIEW] {full2[:200]}...")

# Final history check
hist2 = requests.get(f"{BASE}/api/chat/sessions/{sid}/history", headers=h).json()
log(f"  [DB]      {hist2['count']} messages total (should be 4)")

# ── TEST 3: Out of Scope ──────────────────────────────────────────
log("\n=== TEST 3: Out of Scope ===")
resp3 = requests.post(f"{BASE}/api/chat/sessions/{sid}/message", headers=h,
                      json={"query": "What is the weather today?"}, stream=True)

events3 = []
tokens3 = []
for line in resp3.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        ev = json.loads(line[6:])
        events3.append(ev)
        if ev["t"] == "token":
            tokens3.append(ev["d"])

for ev in events3:
    if ev["t"] != "token":
        log(f'  [{ev["t"].upper():8s}] {json.dumps(ev["d"])[:120]}')

full3 = "".join(tokens3)
log(f"  [TOKENS]  {len(tokens3)} chunks, {len(full3)} chars")
log(f"  [PREVIEW] {full3[:200]}...")

hist3 = requests.get(f"{BASE}/api/chat/sessions/{sid}/history", headers=h).json()
log(f"  [DB]      {hist3['count']} messages total (should be 6)")

log("\n=== ALL TESTS COMPLETE ===")

# Write to file for clean reading
with open("scripts/test_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
