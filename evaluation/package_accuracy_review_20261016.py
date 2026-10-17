"""Package the manually reviewed 2026-10-16 HTTP audit; never grade by keywords.

Requires original local reports and labels bound to their exact response hashes.
Re-running an API report requires manual review and new label bindings.
"""
import json,hashlib,math,statistics
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/accuracy_upgrade_20261015'
LABELS=ROOT/'evaluation/results/accuracy_labels_20261016.json'
FILES={'baseline_core':'before','baseline_extended':'extended_before','final_core':'validated_core','final_extended':'validated_extended','final_expanded':'validated_expanded','untouched':'validated_validation'}
CLASSES={'S':'충분하고 정확한 답변','C':'필요한 확인 질문','P':'타당한 부분 답변','I':'타당한 근거 부족 안내','R':'불필요한 거절·확인 질문','W':'잘못된 업무·사실·조건','E':'실행 오류'}
CONTROL_IDS={'privacy','safety','unavailable','F034','F035','F036','AE021','AE022'}
def digest(v):return hashlib.sha256(v).hexdigest()
def stats(rows):
 if not rows:return {'turns':0,'unique_question_texts':0,'categories':{},'seconds_median':None,'seconds_p95_nearest_rank':None,'seconds_max':None}
 sec=sorted(r['seconds'] for r in rows)
 return {'turns':len(rows),'unique_question_texts':len({r['question'] for r in rows}),'categories':dict(Counter(r['grade'] for r in rows)),'seconds_median':round(statistics.median(sec),3),'seconds_p95_nearest_rank':sec[math.ceil(len(sec)*.95)-1],'seconds_max':max(sec)}
labels=json.loads(LABELS.read_text(encoding='utf8'))
output={'reviewed_on':'2026-10-17','rubric':CLASSES,'protocol':'Manual semantic/source/condition review by the coding assistant, not external human study or keyword auto-scoring. S includes source-limited conditional instructions; C/P/I are safe handling, never sufficient-answer accuracy. R includes unnecessary clarification. W includes important unmarked omissions. Deliberately difficult convenience sample; no population accuracy or zero-hallucination claim. Full source excerpts are separately captured.','runs':{},'records':[]}
for suite,name in FILES.items():
 rawpath=DATA/(name+'.json')
 raw=json.loads(rawpath.read_text(encoding='utf8'))
 assert raw.get('code_unchanged') is True,suite
 assert raw.get('finished_at'), (suite,'incomplete execution')
 expected={'baseline_core':44,'baseline_extended':28,'final_core':54,'final_extended':28,'final_expanded':36,'untouched':22}
 assert len(raw['records'])==expected[suite], (suite,'unexpected turn count')
 assert len(labels[suite])==len(raw['records']),suite
 output['runs'][suite]={k:raw[k] for k in ('started_at','finished_at','commit','case_sha256','code_hashes','code_unchanged')}
 output['runs'][suite]['raw_report_sha256']=digest(rawpath.read_bytes())
 health=raw.get('health_before',{})
 output['runs'][suite]['model']=(health.get('llm') or health.get('ollama') or {}).get('model')
 output['runs'][suite]['runtime']=health
 for r in raw['records']:
  key=f"{r['id']}:{r['turn']}";l=labels[suite][key];b=r['response']
  response_hash=digest(json.dumps(b,ensure_ascii=False,sort_keys=True).encode())
  assert l['response_sha256']==response_hash, (suite,key,'Answer changed; manual review required')
  assert l['category'] in CLASSES and l['reason']
  item={'suite':suite,'id':r['id'],'turn':r['turn'],'question':r['question'],'criterion':r['criterion'],'status':r['status'],'seconds':r['seconds'],'grade':l['category'],'reason':l['reason'],'source_fit':l['source_fit'],'control':r['id'] in CONTROL_IDS,'answer':b.get('answer',''),'is_clarification':b.get('is_clarification',False),'degraded_reason':b.get('degraded_reason'),'sources':[{k:s.get(k) for k in ('title','url','checked_at')} for s in b.get('sources',[])],'response_sha256':digest(json.dumps(b,ensure_ascii=False,sort_keys=True).encode())}
  if l.get('flags'):item['flags']=l['flags']
  output['records'].append(item)
 output['runs'][suite]['summary']=stats([r for r in output['records'] if r['suite']==suite])
final=[r for r in output['records'] if r['suite'].startswith('final_') or r['suite']=='untouched']
final_runs=[v for k,v in output['runs'].items() if k.startswith('final_') or k=='untouched']
assert len({r['commit'] for r in final_runs})==1,'Final runs must use the same commit'
assert all(r['code_hashes']==final_runs[0]['code_hashes'] for r in final_runs),'Final source/code state differs'
output['final_summary']=stats(final)
output['administrative_summary']=stats([r for r in final if not r['control']])
output['controls_summary']=stats([r for r in final if r['control']])
output['factual_answer_summary']=stats([r for r in final if not r['control'] and r['grade'] in ('S','P')])
output['clarification_summary']=stats([r for r in final if not r['control'] and r['grade']=='C'])
output['insufficient_summary']=stats([r for r in final if not r['control'] and r['grade']=='I'])
prior=[r for r in output['records'] if r['suite'].startswith('baseline')]
pairs=[]
for b in prior:
 suite=b['suite'].replace('baseline','final')
 a=next(r for r in final if r['suite']==suite and r['id']==b['id'] and r['turn']==b['turn'])
 assert a['question']==b['question']
 pairs.append((b,a))
output['paired_72']={'before':stats([p[0] for p in pairs]),'after':stats([p[1] for p in pairs]),'note':'Same questions; before Oct15 Gemma2, after Oct17 Gemma4; model switch, source refresh and added procedure are part of the improvement, not isolated algorithm/model/latency ablation.'}
path=ROOT/'evaluation/results/accuracy_review_20261016.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:output[k] for k in ('final_summary','administrative_summary','controls_summary','paired_72')},ensure_ascii=False,indent=2))
