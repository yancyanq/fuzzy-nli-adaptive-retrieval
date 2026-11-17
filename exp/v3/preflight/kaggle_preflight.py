import collections, hashlib, json, math, os, re, urllib.request
from pathlib import Path

URL = 'https://raw.githubusercontent.com/yancyanq/fuzzy-nli-adaptive-retrieval/main/exp/step1/pilot.json'
STOP = set('a an the of in on at to for and or is are was were be been by with from as that this which who whom what when where how did does do it its his her their they he she'.split())
def tok(s): return [w for w in re.findall(r'[a-z0-9]+',s.lower()) if w not in STOP]
def score(corpus,query):
    docs=[collections.Counter(tok(s)) for s in corpus]; n=len(docs)
    lengths=[sum(d.values()) for d in docs]; avg=sum(lengths)/n
    df=collections.Counter(w for d in docs for w in d)
    idf={w:math.log(n-f+0.5)-math.log(f+0.5) for w,f in df.items()}
    floor=0.25*sum(idf.values())/len(idf) if idf else 0
    idf={w:(floor if v<0 else v) for w,v in idf.items()}
    return [sum(idf.get(w,0)*((d[w]*2.5)/(d[w]+1.5*(0.25+0.75*l/avg))) for w in tok(query)) for d,l in zip(docs,lengths)]
def ordering(corpus,query):
    scores=score(corpus,query)
    return sorted(range(len(corpus)),key=lambda i:-scores[i])

def run(data):
    rows=[]
    for ex in data:
        ctx=ex['context']; titles=[x[0] for x in ctx]
        corpus=[t+' '+' '.join(ss) for t,ss in ctx]
        gold=set(t for t,_ in ex['supporting_facts']) & set(titles)
        if not gold: raise ValueError('missing reference title')
        order=ordering(corpus,ex['question']); first=order[:2]
        top=ctx[order[0]]; query=ex['question']+' '+top[0]+' '+(top[1][0] if top[1] else '')
        unused=[i for i in range(len(corpus)) if i not in first]
        more=[unused[j] for j in ordering([corpus[i] for i in unused],query)]
        row={'id':ex['_id']}
        for k in (2,4,6): row['top'+str(k)] = int(gold <= {titles[i] for i in order[:k]})
        for m in (1,2,4): row['2plus'+str(m)] = int(gold <= {titles[i] for i in first+more[:m]})
        rows.append(row)
    return rows

def main():
    path=os.environ.get('PILOT_JSON')
    raw=Path(path).read_bytes() if path else urllib.request.urlopen(URL,timeout=90).read()
    data=json.loads(raw)[:50]
    assert len(data)==50 and len({e['_id'] for e in data})==50
    rows=run(data)
    result={'scope':'exploratory, first 50 prior pilot questions, 10 paragraph candidate pool; reference paragraph title coverage only; no LLM inference','n':len(rows),'data_sha256':hashlib.sha256(raw).hexdigest(),'coverage':{key:sum(r[key] for r in rows)/len(rows) for key in rows[0] if key!='id'},'rows':rows}
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    Path('/kaggle/working/v3_retrieval_preflight.json' if Path('/kaggle/working').exists() else 'experiments/v3-preflight-local/kaggle_preflight_output.json').write_text(json.dumps(result,indent=2))
if __name__ == '__main__': main()
