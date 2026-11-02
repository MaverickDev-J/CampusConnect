"""Join private evaluation metadata with recorded scores; never invent grades."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def summarize(dataset,report):
    labels={case['id']:case for case in dataset['cases']}
    rows=report['cases'];groups={}
    for key in ('all','dev','heldout','exact','paraphrase','multipassage','unanswerable'):
        selected=[row for row in rows if key=='all' or labels[row['case_id']].get('split')==key or labels[row['case_id']]['category']==key]
        strategies={}
        for name in ('dense','hybrid','hybrid_rerank'):
            scored=[row['strategies'][name] for row in selected]
            metrics={}
            for field in ('recall_at_12','ndcg_at_6'):
                values=[score[field] for score in scored if score.get(field) is not None]
                metrics[field]={'mean':statistics.mean(values) if values else None,'samples':len(values)}
            strategies[name]={**metrics,'fallback_cases':sum(bool(s.get('fallback_reason')) for s in scored),
                'effective_strategies':dict(Counter(s.get('strategy','unavailable') for s in scored))}
        pairs=[row for row in selected if all(row['strategies'][name].get('ndcg_at_6') is not None for name in ('hybrid','hybrid_rerank'))]
        actual=[row for row in pairs if not row['strategies']['hybrid_rerank'].get('fallback_reason')]
        deltas=[row['strategies']['hybrid_rerank']['ndcg_at_6']-row['strategies']['hybrid']['ndcg_at_6'] for row in actual]
        groups[key]={'cases':len(selected),'strategies':strategies,'actual_rerank_pairs':len(actual),
            'rerank_vs_hybrid':{'wins':sum(d>1e-9 for d in deltas),'ties':sum(abs(d)<=1e-9 for d in deltas),
                'regressions':sum(d < -1e-9 for d in deltas),'mean_ndcg_delta':statistics.mean(deltas) if deltas else None}}
    return {'dataset_version':dataset['version'],'human_reviewed':bool(dataset.get('reviewed')),
        'label_status':report['label_status'],'retrieval_cases':len(rows),'retrieval_trials':1,
        'embedding_namespace':report['embedding_namespace'],'corpus_version':report['corpus_version'],
        'source_commit':report.get('source_commit'),'source_dirty':report.get('source_dirty'),'groups':groups,
        'limitations':['Provisional source labels require human review.',
            'Fallback rankings are not counted as successful model reranking.',
            'Absent-answer cases require answer/refusal grading and have no retrieval relevance score.',
            'One retrieval trial per question; no stochastic stability or population-level accuracy claim.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--answers',type=Path)
    parser.add_argument('--scope',type=Path)
    parser.add_argument('--output',type=Path,default=Path('storage/evals/summary.json'))
    args=parser.parse_args()
    dataset=json.loads(args.dataset.read_text(encoding='utf-8'))
    report=json.loads(args.report.read_text(encoding='utf-8'))
    summary=summarize(dataset,report)
    summary['dataset_sha256']=hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    summary['report_sha256']=hashlib.sha256(args.report.read_bytes()).hexdigest()
    if args.scope:summary['scope']=json.loads(args.scope.read_text(encoding='utf-8'))
    if args.answers:
        answers=json.loads(args.answers.read_text(encoding='utf-8'))
        summary['answer_sample']={'trials_recorded':len(answers['answers']),
            'failed_trials':sum(bool(row.get('errors')) for row in answers['answers']),
            'grading_status':answers['grading_status'],
            'distinct_cases':len({row['case_id'] for row in answers['answers']})}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('Saved stratified evaluation summary; labels: '+summary['label_status'])
