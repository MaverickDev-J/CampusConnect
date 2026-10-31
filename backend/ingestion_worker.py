"""Run with a restricted worker DATABASE_URL and the shared upload directory."""
import asyncio
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from google import genai
from api.services.postgres_ingestion import IngestionWorker
from api.services.retrieval.embeddings import GeminiEmbeddings
from database.postgres import create_session_factory


async def main():
    load_dotenv()
    engine, factory = create_session_factory(os.environ["DATABASE_URL"])
    key = os.getenv("GEMINI_INGESTION_KEYS") or os.getenv("GEMINI_API_KEY") or os.environ["GEMINI_API_KEYS"]
    client = genai.Client(api_key=key.split(',')[0].strip())
    worker = IngestionWorker(factory, GeminiEmbeddings(client), Path(os.getenv("STORAGE_DIR", "storage")))
    try:
        while True:
            if not await worker.run_once():
                await asyncio.sleep(2)
    finally:
        await client.aio.aclose()
        await engine.dispose()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
