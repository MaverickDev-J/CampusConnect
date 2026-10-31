import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.retrieval.embeddings import EmbeddingSettings, GeminiEmbeddings
from api.services.retrieval.ranking import Candidate, GeminiReranker, reciprocal_rank_fusion


def client(**methods):
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(**methods)))


class EmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.embed = AsyncMock(return_value=SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] + [0.0] * 1535)]))
        self.adapter = GeminiEmbeddings(client(embed_content=self.embed))

    async def test_query_has_instruction_and_dimensions_without_task_type(self):
        result = await self.adapter.query("page replacement")
        request = self.embed.call_args.kwargs
        self.assertEqual(len(result), 1536)
        self.assertEqual(request["contents"], "task: search result | query: page replacement")
        self.assertEqual(request["config"].output_dimensionality, 1536)
        self.assertIsNone(request["config"].task_type)

    async def test_documents_are_independent_requests_in_order(self):
        self.embed.side_effect = [
            SimpleNamespace(embeddings=[SimpleNamespace(values=[n] + [0.0] * 1535)]) for n in (1.0, 2.0)
        ]
        vectors = await self.adapter.documents([("first", "Unit 1"), ("second", None)])
        self.assertEqual([v[0] for v in vectors], [1.0, 2.0])
        self.assertEqual([c.kwargs["contents"] for c in self.embed.call_args_list],
                         ["title: Unit 1 | text: first", "title: none | text: second"])

    async def test_rejects_bad_vectors(self):
        for values in ([1.0], [0.0] * 1536, [float("nan")] * 1536, [float("inf")] * 1536):
            self.embed.return_value.embeddings = [SimpleNamespace(values=values)]
            with self.assertRaises(ValueError):
                await self.adapter.query("test")

    async def test_rejects_aggregated_or_missing_response(self):
        for embeddings in ([], [SimpleNamespace(values=[1]), SimpleNamespace(values=[2])]):
            self.embed.return_value.embeddings = embeddings
            with self.assertRaises(ValueError):
                await self.adapter.document("test")

    async def test_empty_input_makes_no_request(self):
        with self.assertRaises(ValueError):
            await self.adapter.query(" ")
        self.embed.assert_not_called()


class RankingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.candidates = [Candidate("a", "First evidence"), Candidate("b", "Second evidence")]
        self.generate = AsyncMock(return_value=SimpleNamespace(text='{"ranked_ids":["p1","p0"]}'))
        self.reranker = GeminiReranker(client(generate_content=self.generate))

    def test_rrf_rewards_overlap_without_duplicate_votes(self):
        a, b = self.candidates
        self.assertEqual(reciprocal_rank_fusion([a, a, b], [b]), [b, a])

    def test_rrf_ties_are_deterministic(self):
        a, b = self.candidates
        self.assertEqual(reciprocal_rank_fusion([b], [a]), [a, b])

    async def test_valid_ranking_is_mapped_without_fabricated_scores(self):
        result = await self.reranker.rerank("query", self.candidates)
        self.assertEqual([c.chunk_id for c in result.candidates], ["b", "a"])
        self.assertIsNone(result.fallback_reason)
        self.assertIsNone(result.input_tokens)
        self.assertIsNotNone(self.generate.call_args.kwargs["config"].response_json_schema)
        self.assertEqual(self.generate.call_args.kwargs["config"].thinking_config.thinking_level.value, "LOW")
        self.generate.assert_awaited_once()

    async def test_invalid_ids_duplicates_missing_and_malformed_fall_back(self):
        for response in ('{"ranked_ids":["p0","invented"]}', '{"ranked_ids":["p0","p0"]}',
                         '{"ranked_ids":["p0"]}', 'not json', '{"ranked_ids":["p0","p1"],"extra":true}'):
            self.generate.return_value.text = response
            result = await self.reranker.rerank("query", self.candidates)
            self.assertEqual(result.candidates, self.candidates)
            self.assertIsNotNone(result.fallback_reason)

    async def test_quota_error_does_not_retry(self):
        self.generate.side_effect = RuntimeError("429")
        result = await self.reranker.rerank("query", self.candidates)
        self.assertEqual(result.candidates, self.candidates)
        self.generate.assert_awaited_once()

    async def test_timeout_falls_back(self):
        async def slow(**kwargs):
            await asyncio.sleep(1)
        self.generate.side_effect = slow
        self.reranker.timeout = 0.001
        result = await self.reranker.rerank("query", self.candidates)
        self.assertEqual(result.fallback_reason, "timeout")

    async def test_no_request_when_budget_exhausted(self):
        result = await self.reranker.rerank("query", self.candidates, budget_available=False)
        self.assertEqual(result.fallback_reason, "budget_exhausted")
        self.generate.assert_not_called()

    async def test_prompt_size_is_bounded(self):
        result = await self.reranker.rerank("q" * 2001, self.candidates)
        self.assertEqual(result.fallback_reason, "input_budget_exceeded")
        self.generate.assert_not_called()
