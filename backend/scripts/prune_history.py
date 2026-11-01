"""Apply the configured retention policy with worker credentials; no domain data deletion."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from dotenv import dotenv_values
from core.maintenance import prune_history
from database.postgres import create_session_factory


async def run():
    values=dotenv_values(Path(__file__).resolve().parents[1]/'.env')
    engine,factory=create_session_factory(values['WORKER_DATABASE_URL'],pool_size=1)
    try:print(json.dumps(await prune_history(factory)))
    finally:await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:print('Use --apply to prune expired traces, reports, budgets and cache entries in bounded batches.')
    else:
        if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:asyncio.run(run())
        except Exception as exc:
            print('Retention failed ('+type(exc).__name__+'); credentials were not printed.')
            raise SystemExit(1) from None
