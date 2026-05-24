"""
state.py — CampusMind LangGraph State Definition
=================================================
Single source of truth for all data flowing through the agent graph.
Every node reads from and writes to this TypedDict.

FLOW:
  entry_node        → user_profile, chat_history, classroom_context
  router_node       → router_output
  embed_node        → query_embedding  (only on RAG/WEB path)
  retriever_node    → retrieved_chunks, used_sources, no_chunks_found
  web_search_node   → web_search_results
  fast_reject_node  → fast_reject_response
  synthesis_stream  → (streaming tokens — driven from SSE layer)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ── Sub-types ───────────────────────────────────────────────────────


@dataclass
class UserProfile:
    """Loaded from MongoDB ``users`` collection in entry_node."""

    user_id: str
    name: str
    role: Literal["superadmin", "teacher", "student"]
    enrolled_classroom_ids: list[str] = field(default_factory=list)


@dataclass
class ChatMessage:
    """A single message from chat history (last 6 loaded per query)."""

    role: Literal["user", "assistant"]
    content: str


@dataclass
class RetrievedChunk:
    """A single chunk returned from ChromaDB retriever_vector_node."""

    text: str
    source_file: str  # e.g. "ML_Lecture_Unit3.pdf"
    file_type: str    # "pdf", "video", "audio", "image"
    page_number: Optional[int] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    subject: Optional[str] = None
    relevance_score: Optional[float] = None


@dataclass
class RouterOutput:
    """Structured output from router_node (Flash JSON mode)."""

    intent: Literal[
        "RAG_SEARCH",       # → embed → retriever_vector_node
        "WEB_SEARCH",       # → embed → web_search_node
        "DEEP_STUDY",       # → embed → retriever (file-scoped, future)
        "CONVERSATIONAL",   # → synthesis directly (no embed)
        "OUT_OF_SCOPE",     # → fast_reject_node (no LLM, no embed)
    ]
    scope_classroom_id: Optional[str] = None
    target_file_id: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: list[str] = field(default_factory=list)


# ── Main Graph State ────────────────────────────────────────────────


# We use a plain dict at runtime because LangGraph mutates it with
# update() calls between nodes. TypedDict is used for documentation
# and IDE hints only.
GraphState = dict[str, Any]

# ── Documented keys in GraphState ───────────────────────────────────
# query:                str
# session_id:           str
# user_id:              str
# scope_classroom_id:   Optional[str]   — active classroom for this chat
#
# --- entry_node outputs ---
# user_profile:         UserProfile
# classroom_context:    Optional[dict]  — {name, subject, description}
# chat_history:         list[ChatMessage]
#
# --- router_node outputs ---
# router_output:        RouterOutput
# reasoning:            list[str]
#
# --- embed_node outputs (only on RAG/WEB path) ---
# query_embedding:      list[float]
#
# --- retriever_node outputs ---
# retrieved_chunks:     list[RetrievedChunk]
# used_sources:         list[dict]      — ONLY chunks that passed relevance threshold
# no_chunks_found:      bool
#
# --- web_search_node outputs ---
# web_search_results:   list[dict]
#
# --- fast_reject_node outputs ---
# fast_reject_response: str             — hardcoded refusal message
#
# --- synthesis (driven from SSE layer, not a graph node) ---
# final_response:       str             — assembled by SSE after streaming
#
# --- shared metadata ---
# processing_status:    str
# error:                Optional[str]
