"""
graph.py — CampusMind Real LangGraph StateGraph (Production v2)
===============================================================
Proper compiled StateGraph with conditional edges.

FLOW:
  START
    → entry_node
    → router_node
    → [conditional on intent]
        OUT_OF_SCOPE  → fast_reject_node → END
        CONVERSATIONAL → END  (synthesis runs from SSE layer with just history)
        RAG_SEARCH    → embed_node → retriever_node → END
        WEB_SEARCH    → embed_node → web_search_node → END
        DEEP_STUDY    → embed_node → retriever_node → END  (file-scoped)

Synthesis is NOT a graph node — it is an async generator driven by the
SSE endpoint after the graph has populated the full state. This is the
only valid LangGraph pattern for per-token streaming.
"""

from langgraph.graph import END, StateGraph

from .nodes import (
    AgentState,
    embed_node,
    entry_node,
    fast_reject_node,
    retriever_vector_node,
    router_node,
    web_search_node,
)


def _route_after_router(state: AgentState) -> str:
    """Branch after router: skip to fast_reject, synthesis, or embed."""
    intent = state["router_output"].intent
    match intent:
        case "OUT_OF_SCOPE":
            return "fast_reject"
        case "CONVERSATIONAL":
            return END  # No retrieval needed — synthesis uses history only
        case "RAG_SEARCH" | "DEEP_STUDY" | "WEB_SEARCH":
            return "embed"
        case _:
            # Unknown intent → safe fallback to rejection
            return "fast_reject"


def _route_after_embed(state: AgentState) -> str:
    """Branch after embedding: choose retriever or web search."""
    if state.get("error"):
        # Embedding failed — skip to END, SSE will handle the error
        return END

    intent = state["router_output"].intent
    match intent:
        case "WEB_SEARCH":
            return "web_search"
        case _:  # RAG_SEARCH, DEEP_STUDY
            return "retriever"


# ── Build the graph ──────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Assemble the full 6-node LangGraph StateGraph.
    Returns the uncompiled graph (call .compile() on the result).
    """
    g = StateGraph(AgentState)  # Using defined AgentState to ensure merging

    # Register all nodes
    g.add_node("entry", entry_node)
    g.add_node("router", router_node)
    g.add_node("embed", embed_node)
    g.add_node("fast_reject", fast_reject_node)
    g.add_node("retriever", retriever_vector_node)
    g.add_node("web_search", web_search_node)

    # Entry point
    g.set_entry_point("entry")

    # Linear edge: entry → router
    g.add_edge("entry", "router")

    # Conditional branch after router
    g.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "fast_reject": "fast_reject",
            "embed": "embed",
            END: END,  # CONVERSATIONAL path — go straight to END
        },
    )

    # Conditional branch after embed
    g.add_conditional_edges(
        "embed",
        _route_after_embed,
        {
            "retriever": "retriever",
            "web_search": "web_search",
            END: END,  # Embed error path
        },
    )

    # Terminal edges — all retrieval nodes end the graph
    g.add_edge("fast_reject", END)
    g.add_edge("retriever", END)
    g.add_edge("web_search", END)

    return g


# ── Singleton compiled graph ─────────────────────────────────────────

compiled_graph = build_graph().compile()


# ── Debug utilities ──────────────────────────────────────────────────

def print_graph_mermaid() -> None:
    """Print Mermaid diagram for documentation / debugging."""
    print("\n=== CampusMind AI — Graph (v2) ===\n")
    print(compiled_graph.get_graph().draw_mermaid())
    print(f"\n=== Nodes: {len(compiled_graph.get_graph().nodes)} ===\n")
