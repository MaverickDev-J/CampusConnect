"""Small, bounded retention batches using the restricted worker capability."""
from sqlalchemy import text


async def prune_history(factory,*,batch_size=500,max_batches=4):
    totals={'traces':0,'evaluations':0,'budget_calls':0,'caches':0}
    for _ in range(max_batches):
        async with factory() as session,session.begin():
            counts=(await session.execute(text('SELECT public.prune_ai_history(:size)'),{'size':batch_size})).scalar_one()
        for key in totals:totals[key]+=counts[key]
        if max(counts.values())<batch_size:break
    return totals
