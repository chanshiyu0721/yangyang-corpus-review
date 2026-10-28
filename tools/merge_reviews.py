"""Merge team reviews without discarding independent disagreements (stdlib only)."""
import argparse,collections,datetime,json
from pathlib import Path

FIELDS=('status','actual_choice','finding','merge_decision','scene','evidence')
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def fingerprint(answer):return tuple(answer.get(k,'') or '' for k in FIELDS)
def merge_files(pack,baseline,files):
    cases={c['case_id']:c for c in pack['items']};history=collections.defaultdict(list);skipped=0
    allowed={(pack['pack_id'],pack['source_digest'])}|{(p['pack_id'],p['source_digest']) for p in pack.get('accepted_prior_packs',[])}
    originals={e['case_id']:e for e in baseline['entries']}
    for file in files:
        doc=load(file)
        if doc.get('schema')!='yangyang-human-review-v1' or (doc.get('pack_id'),doc.get('source_digest')) not in allowed:raise ValueError(file.name+': review pack does not match')
        if not isinstance(doc.get('entries'),list):raise ValueError(file.name+': entries must be a list')
        seen=set();isbaseline=doc==baseline
        for entry in doc['entries']:
            cid=entry.get('case_id')
            if cid in seen:raise ValueError(file.name+': duplicate case_id '+str(cid))
            seen.add(cid)
            if cid not in cases or entry.get('source_ids')!=cases[cid]['sourceIds']:raise ValueError(file.name+': unknown or mismatched source IDs '+str(cid))
            if entry.get('status','') not in ('','confirmed','uncertain','exclude'):raise ValueError(file.name+': invalid status')
            if any(k in entry and not isinstance(entry[k],str) for k in FIELDS):raise ValueError(file.name+': review fields must be text')
            if not isbaseline and cid in originals and fingerprint(entry)==fingerprint(originals[cid]):skipped+=1;continue
            reviewer='baseline' if isbaseline else str(doc.get('reviewer') or file.stem)
            history[cid].append({'reviewer':reviewer,'source_file':file.name,'exported_at':doc.get('exported_at'),'entry':entry})
    merged=[];conflicts=[]
    for cid,versions in history.items():
        current={}
        for v in versions:
            author=v['reviewer'];stamp=v['entry'].get('updated_at') or v.get('exported_at') or ''
            old=current.get(author);oldstamp=(old['entry'].get('updated_at') or old.get('exported_at') or '') if old else ''
            if not old or stamp>oldstamp:current[author]=v
            elif stamp==oldstamp and fingerprint(v['entry'])!=fingerprint(old['entry']):current[author+'@'+v['source_file']]=v
        votes=list(current.values());base={'case_id':cid,'display_id':cases[cid]['display_id'],'type':cases[cid]['type'],'source_ids':cases[cid]['sourceIds'],'training_export_approved':False}
        if len({fingerprint(v['entry']) for v in votes})>1:
            conflicts.append({'case_id':cid,'display_id':base['display_id'],'opinions':votes})
            result={**base,'status':'uncertain','finding':'存在不同核验意见，请查看 conflicts.json 后裁定。','evidence':'参见 conflicts.json：'+cid,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        else:result={**base,**{k:v for k,v in votes[0]['entry'].items() if k in FIELDS+('updated_at',)},'training_export_approved':False}
        merged.append(result)
    return merged,conflicts,dict(history),skipped

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('reviews',type=Path);parser.add_argument('--output',type=Path,default=Path('merged'));args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];pack=load(root/'data/review_pack.json');baseline=load(root/'reviews/baseline_20261027.json')
    files=sorted(args.reviews.glob('*.json'));basepath=root/'reviews/baseline_20261027.json'
    if not any(p.resolve()==basepath.resolve() for p in files):files.insert(0,basepath)
    merged,conflicts,history,skipped=merge_files(pack,baseline,files)
    args.output.mkdir(parents=True,exist_ok=True)
    values={'merged_review.json':{'schema':'yangyang-human-review-v1','pack_id':pack['pack_id'],'source_digest':pack['source_digest'],'reviewer':'team_merge','exported_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':merged},'conflicts.json':conflicts,'review_history.json':history,'summary.json':{'files':len(files),'merged_items':len(merged),'conflicting_items':len(conflicts),'unchanged_baseline_copies_skipped':skipped,'status_counts':dict(collections.Counter(e.get('status','draft') for e in merged)),'training_export_approved':False}}
    for name,data in values.items():(args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(values['summary.json'],ensure_ascii=False))
if __name__=='__main__':main()
