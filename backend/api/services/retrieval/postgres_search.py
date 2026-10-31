"""Exact, scoped PostgreSQL retrieval baseline; ANN is enabled only after evaluation."""
import math
import re

from sqlalchemy import text
from api.services.retrieval.ranking import Candidate, reciprocal_rank_fusion


class PostgresSearch:
    def __init__(self, session, *, namespace="gemini-embedding-2:1536:search-v1"):
        self.session = session
        self.namespace = namespace

    async def search(self, query, embedding, *, classroom_id, file_id=None, strategy="hybrid", limit=12):
        if strategy not in {"dense", "hybrid", "lexical"}:
            raise ValueError("Unsupported retrieval strategy")
        if not classroom_id or not query.strip() or not 1 <= limit <= 20:
            raise ValueError("A query, explicit classroom, and bounded limit are required")
        if strategy != "lexical" and (embedding is None or len(embedding) != 1536 or not all(math.isfinite(v) for v in embedding) or not any(embedding)):
            raise ValueError("Expected a finite nonzero 1536-dimensional vector")
        scope = """
            FROM chunks c
            JOIN files f ON f.file_id = c.file_id AND f.classroom_id = c.classroom_id
            JOIN file_revisions r ON r.file_id = c.file_id AND r.revision = c.revision
            WHERE c.classroom_id = :classroom_id
              AND public.can_read_classroom(c.classroom_id)
              AND (:file_id IS NULL OR c.file_id = :file_id)
              AND f.status = 'ready' AND f.active_revision = c.revision
              AND r.status = 'ready' AND r.embedding_namespace = :namespace
              AND c.embedding IS NOT NULL
        """
        params = {
            "classroom_id": classroom_id, "file_id": file_id, "namespace": self.namespace,
            "vector": '[' + ','.join(str(float(v)) for v in embedding) + ']' if embedding else None,
        }
        # Cast nullable parameters explicitly for PostgreSQL prepared statements.
        scope = scope.replace(":file_id IS NULL", "CAST(:file_id AS text) IS NULL")
        dense_candidates = []
        if strategy != "lexical":
            dense = await self.session.execute(text(
                "SELECT c.chunk_id, c.text " + scope +
                " ORDER BY c.embedding <=> CAST(:vector AS vector), c.chunk_id LIMIT 30"
            ), params)
            dense_candidates = [Candidate(row.chunk_id, row.text) for row in dense]
        if strategy == "dense":
            return dense_candidates[:limit]
        # Broad lexical recall avoids requiring every question word to match.
        tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:64]
        params["lexical_query"] = " OR ".join(tokens)
        lexical = await self.session.execute(text(
            "SELECT c.chunk_id, c.text " + scope +
            " AND c.lexical @@ websearch_to_tsquery('english', :lexical_query)"
            " ORDER BY ts_rank_cd(c.lexical, websearch_to_tsquery('english', :lexical_query)) DESC, c.chunk_id LIMIT 30"
        ), params)
        return reciprocal_rank_fusion(
            [Candidate(row.chunk_id, row.text) for row in lexical], dense_candidates, limit=limit,
        )
