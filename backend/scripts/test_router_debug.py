"""Debug: test the router_node in isolation to see what it actually returns."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from api.agent.nodes import router_node
from api.agent.state import UserProfile

async def test():
    queries = [
        "What is backpropagation?",
        "What do the uploaded notes say about backpropagation?",
        "Find information from my course material about neural networks",
        "Explain sorting algorithms from my notes",
        "Thanks for the help!",
        "What is the weather today?",
    ]

    profile = UserProfile(
        user_id="test", name="Test Student", role="student", year=3, branch="COMP"
    )

    for q in queries:
        state = {
            "query": q,
            "user_id": "test",
            "session_id": "test",
            "user_profile": profile,
            "chat_history": [],  # empty history = no conversational context
            "query_embedding": [0.0] * 768,
        }
        result = await router_node(state)
        ro = result["router_output"]
        print(f"  QUERY: {q}")
        print(f"  INTENT: {ro.intent}  scope_subject={ro.scope_subject}  conf={ro.confidence}")
        print()

asyncio.run(test())
