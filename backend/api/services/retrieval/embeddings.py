"""Gemini Embedding 2 text adapter; one request per input prevents aggregation."""

import asyncio
import math
from dataclasses import dataclass

from google.genai import types
from core.gemini_budget import BudgetedGemini


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str = "gemini-embedding-2"
    dimensions: int = 1536
    format_version: str = "search-v1"
    timeout_seconds: float = 30
    concurrency: int = 2

    def __post_init__(self):
        if self.model != "gemini-embedding-2" or self.dimensions not in (768, 1536, 3072):
            raise ValueError("Unsupported embedding configuration")
        if self.concurrency < 1 or self.timeout_seconds <= 0:
            raise ValueError("Invalid embedding resource limits")

    @property
    def namespace(self):
        return f"{self.model}:{self.dimensions}:{self.format_version}"


class GeminiEmbeddings:
    def __init__(self, client, settings=EmbeddingSettings(), *, budget=None):
        self.client = BudgetedGemini(client, budget, 'embed_query') if client and budget else client
        self.document_client = BudgetedGemini(client, budget, 'embed_document') if client and budget else client
        self.settings = settings
        self._slots = asyncio.Semaphore(settings.concurrency)

    async def _embed(self, text: str, *, document=False) -> list[float]:
        async with self._slots:
            response = await asyncio.wait_for(
                (self.document_client if document else self.client).aio.models.embed_content(
                    model=self.settings.model,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self.settings.dimensions),
                ), timeout=self.settings.timeout_seconds,
            )
        if not response.embeddings or len(response.embeddings) != 1:
            raise ValueError("Expected exactly one embedding per input")
        values = response.embeddings[0].values
        if values is None or len(values) != self.settings.dimensions:
            raise ValueError("Embedding dimension mismatch")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Embedding contains non-finite values")
        if not any(values):
            raise ValueError("Embedding has zero norm")
        return list(values)

    async def query(self, query: str):
        if not query.strip():
            raise ValueError("Query is empty")
        return await self._embed(f"task: search result | query: {query}")

    async def document(self, text: str, title: str | None = None):
        if not text.strip():
            raise ValueError("Document is empty")
        return await self._embed(f"title: {title or 'none'} | text: {text}", document=True)

    async def documents(self, documents: list[tuple[str, str | None]]):
        # Bounded batches avoid scheduling a task for every chunk of a large upload.
        results = []
        for start in range(0, len(documents), self.settings.concurrency):
            batch = documents[start:start + self.settings.concurrency]
            results.extend(await asyncio.gather(*(self.document(text, title) for text, title in batch)))
        return results
