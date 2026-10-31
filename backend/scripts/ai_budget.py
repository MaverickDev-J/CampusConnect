"""Inspect or lower application caps using the migration-owner DATABASE_URL.

Examples (from backend):
  uv run python -m scripts.ai_budget --show
  uv run python -m scripts.ai_budget --model gemini-3.8-flash --rpm 3
These are application caps, not a query of Google's actual project entitlements.
"""
import argparse
import json
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default=os.getenv('GEMINI_BUDGET_PROJECT','campusconnect-default'))
    parser.add_argument('--model',choices=['gemini-3.8-flash','gemini-embedding-2'])
    parser.add_argument('--show',action='store_true')
    fields = ['rpm','input_tpm','rpd','concurrent_requests','reserve_rpm','reserve_tpm','reserve_rpd','reserve_slots']
    for field in fields:
        parser.add_argument('--'+field.replace('_','-'),type=int)
    args = parser.parse_args()
    changes = {field:getattr(args,field) for field in fields if getattr(args,field) is not None}
    if changes and not args.model:
        parser.error('--model is required to change limits')
    if not changes and not args.show:
        parser.error('Use --show or supply a limit to change')
    url = os.environ.get('DATABASE_URL','').replace('postgresql+psycopg://','postgresql://',1)
    if not url:
        parser.error('Set the migration-owner DATABASE_URL; the API role cannot inspect or change policies')
    try:
        with psycopg.connect(url,row_factory=dict_row) as conn:
            if changes:
                assignments = sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(field)) for field in changes)
                updated = conn.execute(sql.SQL('UPDATE ai_budget_policies SET {} WHERE project_key=%s AND model=%s').format(assignments),
                    [*changes.values(),args.project,args.model])
                if not updated.rowcount:
                    parser.error('No policy exists for this project/model')
            rows = conn.execute('''SELECT p.*,count(c.call_id) FILTER(WHERE c.quota_day=
              (clock_timestamp() AT TIME ZONE 'America/Los_Angeles')::date) AS requests_today
              FROM ai_budget_policies p LEFT JOIN ai_budget_calls c USING(project_key,model)
              WHERE p.project_key=%s GROUP BY p.project_key,p.model ORDER BY p.model''',(args.project,)).fetchall()
        print(json.dumps(rows,indent=2,default=str))
    except psycopg.errors.CheckViolation:
        parser.error('Invalid limits: each reserve must be smaller than its corresponding total; totals must be positive')
    except psycopg.Error:
        parser.error('Database operation failed; check connectivity, migrations and migration-owner permissions')


if __name__=='__main__':
    main()
