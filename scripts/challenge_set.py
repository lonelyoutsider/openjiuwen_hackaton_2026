"""Authored offline stress suite: 100 tasks, 40 solvable families + 20 missing-data cases.

No third-party task text/data/code is copied. Inspiration and limitations are in
 docs/research-2026-11-13.md. Labels and reference implementations never enter task.json.
"""
import csv
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
import heapq
import io
import itertools
import json
from pathlib import Path
import random

VERSION = 'challenge-v1'
PARTITIONS = ('all', 'smoke', 'calibration', 'confirmation')


def table(header, rows, delimiter=','):
    out = io.StringIO(); writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(header); writer.writerows(rows)
    return out.getvalue()


def spec(family, kind, instruction, expected, files=None, **extra):
    check='exact_str'
    if kind != 'coding' and expected is not None:
        try:
            if Decimal(expected).is_finite():check='exact_number'
        except Exception:pass
    return dict(family=family, task_type=kind, instruction=instruction, expected=expected,
                files=files or {}, check=check, **extra)


def math_cases(v):
    n = 3 + v
    yield spec('weighted', 'math', f'There are {n} batches of 12 items and 5 batches of 18 items. What is the mean number of items per batch? Give a reduced fraction a/b, including /1 for an integer.', str(Fraction(n*12+90,n+5)))
    price=Decimal(125+25*v); answer=price*Decimal('.8')*Decimal('1.15')
    yield spec('discount_tax', 'math', f'A price of {price} is discounted by 20 percent and then taxed at 15 percent on the discounted price. Give the final numeric price.', str(answer))
    q=127+v*13
    yield spec('capacity', 'math', f'{q} parcels must be shipped. A van carries at most 24 parcels. Each trip costs 17 credits plus 2 credits per parcel carried. What is the minimum total cost? Give an integer.', str(((q+23)//24)*17+2*q))
    count=173+v*41
    yield spec('cycles', 'math', f'A lamp is ON for 7 seconds then OFF for 4 seconds, repeatedly. It starts ON at time zero. How many seconds is it ON during the first {count} seconds?', str(count//11*7+min(count%11,7)))
    edges=[('A','B',4+v),('A','C',2),('C','B',1),('B','D',3),('C','D',9),('D','E',2+v),('B','E',11)]
    dist={'A':0}; todo=[(0,'A')]
    while todo:
        d,u=heapq.heappop(todo)
        if d!=dist[u]:continue
        for a,b,w in edges:
            if a==u and d+w<dist.get(b,10**9):dist[b]=d+w;heapq.heappush(todo,(d+w,b))
    yield spec('shortest_path','math','Using the directed weighted graph in graph.json, give the minimum total weight from A to E, as an integer.',str(dist['E']),{'graph.json':json.dumps(edges)})
    red=4+v;blue=5
    prob=Fraction(red*(red-1),(red+blue)*(red+blue-1))
    yield spec('probability','math',f'A bag contains {red} red and {blue} blue balls. Two balls are sampled uniformly without replacement. What is the probability both are red? Return the reduced fraction a/b.',f'{prob.numerator}/{prob.denominator}')
    start=date(2026,11,12+v);days=9+v;end=start;left=days
    while left:
        end+=timedelta(days=1)
        if end.weekday()<5:left-=1
    yield spec('business_days','math',f'Starting after {start.isoformat()}, advance {days} business days. Business days are Monday through Friday, and there are no holidays. The starting date is not counted. Give the resulting YYYY-MM-DD date.',end.isoformat())
    target=11+v
    ways=[0]*(target+1);ways[0]=1
    for coin in [1,3,4]:
        for k in range(coin,target+1):ways[k]+=ways[k-coin]
    yield spec('coin_change','math',f'Using unlimited coins of values 1, 3 and 4, how many unordered combinations total {target}? The order of coins does not distinguish combinations. Return an integer.',str(ways[target]))
    # Independently enumerate integer solutions; no learned or task-ID based oracle.
    total=34+v*6;sol=[(a,b) for a in range(30) for b in range(30) if a+b==total and 2*a+4*b==total*3+2]
    yield spec('linear_system','math',f'A farm has {total} animals, all chickens or rabbits, with {total*3+2} legs in total. How many rabbits are there? Return an integer.',str(sol[0][1]) if sol else None)
    values=[7,-2,5,1+v,-4,9,0,-3]
    best=max(sum(values[i:j]) for i in range(len(values)) for j in range(i+1,len(values)+1))
    yield spec('subarray','math','numbers.json is a list of integers. Find the maximum sum of any nonempty contiguous subarray. Return the sum only.',str(best),{'numbers.json':json.dumps(values)})


def search_cases(v):
    name=('Mira','Sora')[v];city=('Riga','Oslo')[v]
    yield spec('three_hop','search',f'Using kb/, give the headquarters city of the institute that contains the laboratory operating Project {name}. Return only the city.',city,{
        'kb/projects.md':f'Project {name} is operated by Delta Lab. Project Nova is operated by Echo Lab.\n',
        'kb/labs.md':'Delta Lab is part of Quartz Institute. Echo Lab is independent.\n',
        'kb/cities.md':f'Quartz Institute headquarters: {city}. Delta Lab field office: Bern. Echo Lab headquarters: Lyon.\n'})
    rows=[['Oak',2008+v,'solar;battery'],['Elm',2005,'solar;diesel'],['Ash',2007+v,'battery;solar'],['Pine',2001,'battery;wind']]
    yield spec('conjunction','search','Using stations.csv, return the station name with the earliest commissioned year among stations having BOTH solar and battery equipment. Return only its name.','Ash',{'stations.csv':table(['station','year','equipment'],rows)})
    year=2023+v
    yield spec('temporal_update','search',f'According to the dated entries in records.md, who was the director on {year}-06-01? Appointments replace the previous director from their effective date. Return the full name.','Lea Chen',{'records.md':f'2020-01-01: Arin Moss appointed director.\n{year}-03-01: Lea Chen appointed director.\n{year}-09-01: Niko Hart appointed director.\n'})
    yield spec('alias_resolution','search',f'The researcher whose registry ID is P-{31+v} has a listed publishing alias. In awards.md, find the award received under that alias. Return only the award name.','Silver Quill',{'registry.csv':table(['id','legal_name','alias'],[[f'P-{31+v}','Robin Vale','R. North'],['P-99','Riley Vale','R. Vale']]),'awards.md':'R. Vale received Bronze Leaf. R. North received Silver Quill.\n'})
    yield spec('negation','search','Find the expedition in trips.json that visited Iceland but did NOT visit Norway. Return the expedition name only.','Vega'+str(v),{'trips.json':json.dumps([{'name':'Lyra','places':['Iceland','Norway']},{'name':'Vega'+str(v),'places':['Iceland','Sweden']},{'name':'Altair','places':['Sweden']}])})
    # The sought fact is outside initial_context's 8k/file and a plain read's 16k.
    long=''.join(f'Archive entry {i}: routine maintenance completed; no ownership changes.\n' for i in range(650))
    long+=f'Control record: asset Q-{80+v} has registered owner Meridian Cooperative.\n'
    yield spec('long_tail','search',f'Find the registered owner of asset Q-{80+v} in archive.txt. Read/search the complete file if necessary. Return the legal name only.','Meridian Cooperative',{'archive.txt':long},stress='answer beyond 16k characters')
    yield spec('conflicting_sources','search','policy.md identifies the authoritative ledger. Give the capacity from that ledger; disregard drafts and cached reports. Return only the integer.',str(74+v),{'policy.md':'Only final/ledger.csv is authoritative. Drafts and cache are obsolete.\n','00_cached.md':'Capacity: 999.\n','draft/ledger.csv':'capacity\n888\n','final/ledger.csv':f'capacity\n{74+v}\n'})
    yield spec('entity_disambiguation','search','Give the birthplace of Alex Reed whose registry ID is R2, not R1. Return only the city.','Tartu',{'people.json':json.dumps([{'id':'R1','name':'Alex Reed','birthplace':'Turku'},{'id':'R2','name':'Alex Reed','birthplace':'Tartu','age':30+v}])})
    yield spec('unicode_keys','search','In catalog.json, find the title whose code equals "café" after Unicode NFC normalization. Return its exact title.','Blue Atlas',{'catalog.json':json.dumps([{'code':'cafe','title':'Red Atlas'},{'code':'cafe\u0301','title':'Blue Atlas','revision':v}])})
    answer=('Baltic Survey','Northern Survey')[v]
    yield spec('nested_documents','search','Using the index and its referenced local document, return the title of report R7. Do not use unrelated titles.',answer,{'index.json':json.dumps({'R7':'reports/2026/record.json','R8':'reports/2025/record.json'}),'reports/2026/record.json':json.dumps({'title':answer}),'reports/2025/record.json':'{"title":"Obsolete Survey"}'})


def data_cases(v):
    rows=[['east','12.50',str(2+v)],['west','99','1'],['east','7.25','-1'],['east','3','4']]
    yield spec('signed_revenue','data_analysis','In orders.csv, sum price times signed quantity for east rows only. Negative quantities are refunds. Return the numeric net revenue.', str(Decimal('29.75')+Decimal('12.50')*v),{'orders.csv':table(['region','price','quantity'],rows)})
    expected=3+(v+2)*5
    yield spec('two_table_join','data_analysis','Join orders.csv to prices.csv by sku and sum signed quantity times price for retail rows only. Return the numeric result.',str(expected),{'orders.csv':table(['sku','qty','channel'],[['A','2','retail'],['B','1','wholesale'],['A','-1','retail'],['C',str(v+2),'retail']]),'prices.csv':'sku,price\nA,3\nB,8\nC,5\n'})
    yield spec('dedup_events','data_analysis','events.jsonl is newline-delimited JSON. Count unique users with any paid event of value >= 10. Ignore other event types. Return an integer.','2',{'events.jsonl':'\n'.join(json.dumps(x) for x in [{'user':'x','type':'paid','value':11+v},{'user':'x','type':'paid','value':30},{'user':'y','type':'view','value':100},{'user':'z','type':'paid','value':10}])})
    yield spec('csv_quoting','data_analysis','In notes.csv, sum amount where tag is exactly "alpha,beta". Commas inside quoted fields belong to the field. Return only the integer.',str(12+v),{'notes.csv':table(['tag','amount'],[['alpha,beta',7+v],['alpha',999],['alpha,beta',5]])})
    rows=[['d',2],['b',7+v],['a',7+v],['d',3]]
    yield spec('group_tie','data_analysis','Sum value per name in scores.csv. Return the name with the largest total, breaking equal totals by lexicographically smallest name.','a',{'scores.csv':table(['name','value'],rows)})
    start=100;num=1800
    data=table(['id','amount'],((i,1 if i<num-1 else 77+v) for i in range(num)))
    yield spec('long_aggregate','data_analysis','large.csv contains all records. Sum amount over ALL rows, not just a displayed preview. Return an integer.',str(num-1+77+v),{'large.csv':data},stress='last row outside initial preview')
    yield spec('missing_values','data_analysis','values.csv uses empty fields and NA as missing. Ignore missing readings and compute the arithmetic mean of valid readings. Return a numeric answer.',str((10+20+30+6*v)/3),{'values.csv':table(['reading'],[[10+v],[''],['NA'],[20+2*v],[30+3*v]])})
    yield spec('timezone','data_analysis','events.csv timestamps include UTC offsets. Count rows whose UTC calendar date is 2026-11-13. Return an integer.','2',{'events.csv':'time\n2026-11-13T00:30:00+03:00\n2026-11-13T23:30:00-02:00\n2026-11-13T09:00:00+03:00\n2026-11-14T00:30:00+02:00\n'})
    nested=spec('nested_json','data_analysis','orders.json contains nested items. Sum quantity times unit_price across all items of orders with status "complete". '+('Return a JSON object with exactly one key "total" and its numeric value.' if v else 'Return the numeric total.'),json.dumps({'total':19+v}) if v else str(19+v),{'orders.json':json.dumps([{'status':'complete','items':[{'quantity':2,'unit_price':5},{'quantity':1,'unit_price':9+v}]},{'status':'cancelled','items':[{'quantity':100,'unit_price':99}]}])})
    if v:nested['check']='exact_json'
    yield nested
    yield spec('utf8_bom_tsv','data_analysis','Read records.tsv as UTF-8 (it has a BOM) with tab-separated columns. Sum score for active=1 rows. Return an integer.',str(11+v),{'records.tsv':'\ufeff'+table(['name','active','score'],[['A',1,4+v],['B',0,999],['C',1,7]],delimiter='\t')})


# Reference source is held by the offline evaluator, never copied into workspace.
CODING = [
('slug','Implement slug(text): strip surrounding whitespace, Unicode casefold, split on whitespace and join words by a single hyphen. Preserve punctuation inside words.',
 'def slug(text):\n    return text.lower().replace(" ", "-")\n',
 'def slug(text):\n    return "-".join(text.casefold().split())\n',
 [('slug("Hello World")','hello-world'),('slug(" a  b ")','a-b')],
 'for s in ("Straße", " A\\tB\\nC ", "", " déjà   VU "):\n    assert slug(s) == "-".join(s.casefold().split())\n'),
('unique','Implement unique(values): accept any finite iterable of hashable values and return a list containing the first occurrence of each value, preserving order.',
 'def unique(values):\n    return sorted(set(values))\n',
 'def unique(values):\n    return list(dict.fromkeys(values))\n',
 [('unique([3,1,3,2])',[3,1,2]),('unique([])',[])],
 'assert unique(iter([3,1,3,2])) == [3,1,2]\nassert unique(["x",1,"x",None,1]) == ["x",1,None]\n'),
('chunks','Implement chunks(values, size): accept a finite iterable, return lists of consecutive chunks including an incomplete final chunk. Reject size <= 0 with ValueError.',
 'def chunks(values, size):\n    return [values[i:i+size] for i in range(0,len(values)-size,size)]\n',
 'def chunks(values, size):\n    if size <= 0: raise ValueError("size")\n    xs=list(values)\n    return [xs[i:i+size] for i in range(0,len(xs),size)]\n',
 [('chunks([1,2,3,4,5],2)',[[1,2],[3,4],[5]]),('chunks([],2)',[])],
 'assert chunks(iter(range(7)),3) == [[0,1,2],[3,4,5],[6]]\nfor n in (0,-1):\n    try: chunks([1],n)\n    except ValueError: pass\n    else: raise AssertionError("invalid size accepted")\n'),
('interval_union','Implement interval_union(intervals): for half-open intervals [start,end), discard empty intervals, merge overlapping or touching intervals, sort results, preserve the input. Return a list of tuples.',
 'def interval_union(intervals):\n    return sorted(intervals)\n',
 'def interval_union(intervals):\n    out=[]\n    for a,b in sorted(intervals):\n        if a >= b: continue\n        if out and a <= out[-1][1]: out[-1]=(out[-1][0],max(b,out[-1][1]))\n        else: out.append((a,b))\n    return out\n',
 [('interval_union([(3,5),(1,3)])',[(1,5)]),('interval_union([])',[])],
 'xs=[(4,8),(1,2),(2,6),(9,9)];before=xs[:]\nassert interval_union(iter(xs)) == [(1,8)]\nassert interval_union(xs)==[(1,8)] and xs==before\n'),
('toposort','Implement toposort(nodes, edges): edges (a,b) require a before b. Include isolated nodes and deduplicate edges. Among currently available nodes choose the lexicographically smallest. Raise ValueError on a cycle. Return a list.',
 'def toposort(nodes, edges):\n    return sorted(nodes)\n',
 'def toposort(nodes, edges):\n    import heapq\n    adj={n:set() for n in nodes};deg=dict.fromkeys(nodes,0)\n    for a,b in edges:\n        if b not in adj[a]: adj[a].add(b);deg[b]+=1\n    q=[n for n in deg if deg[n]==0];heapq.heapify(q);out=[]\n    while q:\n        a=heapq.heappop(q);out.append(a)\n        for b in adj[a]:\n            deg[b]-=1\n            if deg[b]==0:heapq.heappush(q,b)\n    if len(out)!=len(deg):raise ValueError("cycle")\n    return out\n',
 [('toposort(["a","b","c"],[("b","a")])',['b','a','c'])],
 'assert toposort(["a","b","c"],[("a","b"),("a","b")])==["a","b","c"]\ntry:toposort(["a","b"],[("a","b"),("b","a")])\nexcept ValueError:pass\nelse:raise AssertionError("cycle accepted")\n'),
('run_length','Implement encode_runs(values): accept any finite iterable and return a list of (value,count) tuples for consecutive equal values, in order. Empty input returns [].',
 'def encode_runs(values):\n    return [(x,values.count(x)) for x in set(values)]\n',
 'def encode_runs(values):\n    out=[]\n    for x in values:\n        if out and out[-1][0]==x:out[-1]=(x,out[-1][1]+1)\n        else:out.append((x,1))\n    return out\n',
 [('encode_runs([1,1,2,1])',[(1,2),(2,1),(1,1)]),('encode_runs([])',[])],
 'assert encode_runs(iter([None,None,0,0,False,2]))==[(None,2),(0,3),(2,1)]\n'),
('multifile_money','Fix total(rows) in totals.py and cents(text) in money.py. Decimal currency strings must convert exactly to integer cents; total sums cents(price)*signed integer quantity. Preserve tests.',
 'def cents(text):\n    return int(float(text)*100)\n',
 'from decimal import Decimal\ndef cents(text):\n    return int(Decimal(text)*100)\n',
 [('total([("1.15",2),("0.29",-1)])',201)],
 'assert cents("0.29")==29\nassert total([("0.29",3),("1.15",-1)])==-28\n'),
('binary_search','Implement lower_bound(values, target) for a sorted sequence: return the first index whose value is >= target, or len(values) when none. Handle duplicates and empty input.',
 'def lower_bound(values, target):\n    return values.index(target)\n',
 'def lower_bound(values, target):\n    import bisect\n    return bisect.bisect_left(values,target)\n',
 [('lower_bound([1,2,2,4],2)',1),('lower_bound([],3)',0)],
 'import bisect\nfor xs in ([],[1],[1,1,2,5],[-3,0,9]):\n    for t in range(-5,12): assert lower_bound(xs,t)==bisect.bisect_left(xs,t)\n'),
('flatten','Implement flatten(values): recursively flatten nested lists and tuples into a new list. Treat other objects, including strings, as atomic. Preserve input.',
 'def flatten(values):\n    return list(values)\n',
 'def flatten(values):\n    out=[]\n    for x in values:\n        if isinstance(x,(list,tuple)):out.extend(flatten(x))\n        else:out.append(x)\n    return out\n',
 [('flatten([1,[2,(3,4)]])',[1,2,3,4]),('flatten([])',[])],
 'assert flatten(["ab",(),[None,[[5]]]])==["ab",None,5]\n'),
('lru','Implement LRU(capacity) with get(key) returning the value or -1, and put(key,value). A get hit or put marks the key most recent. Evict the least recent when over capacity. Capacity zero stores nothing.',
 'class LRU:\n    def __init__(self, capacity):self.capacity=capacity;self.data={}\n    def get(self,key):return self.data.get(key,-1)\n    def put(self,key,value):self.data[key]=value\n',
 'from collections import OrderedDict\nclass LRU:\n    def __init__(self,capacity):self.capacity=capacity;self.data=OrderedDict()\n    def get(self,key):\n        if key not in self.data:return -1\n        self.data.move_to_end(key);return self.data[key]\n    def put(self,key,value):\n        if self.capacity<=0:return\n        self.data[key]=value;self.data.move_to_end(key)\n        if len(self.data)>self.capacity:self.data.popitem(last=False)\n',
 [('(lambda c: (c.put("a",1),c.get("a")))(LRU(2))',(None,1))],
 'c=LRU(2);c.put("a",1);c.put("b",2);assert c.get("a")==1;c.put("c",3);assert c.get("b")==-1\nz=LRU(0);z.put("x",2);assert z.get("x")==-1\n')]


def coding_cases(v):
    for name,instruction,buggy,reference,checks,private in CODING:
        if v:
            mutants = {
                'slug': 'def slug(text):\n    return "-".join(text.lower().split())\n',
                'unique': 'def unique(values):\n    return list(set(values))\n',
                'chunks': 'def chunks(values,size):\n    if size<=0:raise ValueError("size")\n    return [values[i:i+size] for i in range(0,len(values),size) if i+size<=len(values)]\n',
                'interval_union': reference.replace('a <= out[-1][1]', 'a < out[-1][1]'),
                'toposort': reference.replace('if b not in adj[a]: adj[a].add(b);deg[b]+=1', 'adj[a].add(b);deg[b]+=1'),
                'run_length': 'def encode_runs(values):\n    return [(x,1) for x in values]\n',
                'multifile_money': reference,
                'binary_search': reference.replace('bisect_left', 'bisect_right'),
                'flatten': reference.replace('(list,tuple)', 'list'),
                'lru': reference.replace('self.data.move_to_end(key);return self.data[key]', 'return self.data[key]')}
            buggy=mutants[name]
        module='impl';files={'impl.py':buggy}
        if name=='multifile_money':
            module='totals';files={'money.py':buggy,'totals.py':'from money import cents\ndef total(rows):\n    return sum(cents(p)*abs(q) for p,q in rows)\n'}
            refs={'money.py':reference,'totals.py':'from money import cents\ndef total(rows):\n    return sum(cents(p)*q for p,q in rows)\n'}
            imports='from totals import *\nfrom money import cents\n'
        else:refs={'impl.py':reference};imports='from impl import *\n'
        test='import unittest\n'+imports+'class Checks(unittest.TestCase):\n'
        for i,(expr,expected) in enumerate(checks):
            test+=f'    def test_{i}(self): self.assertEqual({expr}, {expected!r})\n'
        # A second mutation, not a repeated identical source/test fixture.
        if v and name=='slug':test+='    def test_casefold(self): self.assertEqual(slug("Straße"),"strasse")\n'
        files['test_contract.py']=test
        item=spec(name,'coding',instruction+' Edit existing source files only. Keep tests unchanged.','tests_pass',files,private_check=imports+private,reference_sources=refs)
        item['check']='unittest'
        yield item


def missing_cases(kind):
    if kind=='math':
        tasks=[('distance','A train travels for 3 hours. What exact distance did it travel?','Only the duration is recorded; no speed or route distance is available.'),('rectangle','A rectangle has perimeter 28. What is its exact area?','Sides are positive real values; no other constraints are given.'),('probability','What is the exact probability that the next draw is red?','Draw protocol and counts of colors are not recorded.'),('conversion','Convert 500 credits to exact USD.','No exchange rate or definition of a credit is supplied.'),('sequence','What is the uniquely determined next integer after 2,4,8?','No generating rule, recurrence or further constraint is supplied.')]
    elif kind=='search':
        tasks=[('birthplace','Give the birthplace of Dana Vale.','Dana Vale works in Rome. No birthplace is recorded.'),('owner','Who legally owns Project Falcon?','Falcon is operated by Cedar Lab; ownership is not stated.'),('appointment','Who is the director in 2026?','Ari was director in 2020. Subsequent records are unavailable.'),('identity','Which Alex Reed won the prize?','There are two distinct people named Alex Reed. The award mentions only that name and no unique identifiers.'),('date','Give the exact YYYY-MM-DD date when Atlas launched.','Atlas launched sometime in 2024; day and month are unrecorded.')]
    elif kind=='data_analysis':
        tasks=[('profit','Give exact net profit.','Revenue is 1000. All cost values are absent.'),('population','Give the exact mean of all transactions.','The available rows (10 and 30) are only a sample; unobserved row values/count are unavailable.'),('weighted','Give the exact weighted mean of group scores.','The scores are 3 and 8, but neither group weight is recorded.'),('join','Give revenue by multiplying quantities and unit prices.','Quantities A=2,B=3 are recorded, but there is no price table.'),('future','Give the exact total sales on 2027-01-01.','Only sales from 2026 are present; no deterministic rule for future sales is specified.')]
    else:
        tasks=[('lookup','Implement price(code) returning the exact official price for every product code.','Only one example price is known; the full external product-price table is unavailable.'),('checksum','Implement official_checksum(text) exactly matching the proprietary checksum.','The checksum algorithm and expected outputs are not supplied.'),('policy','Implement permitted(user, action) using the company access rules.','The access-control policy is absent. Do not invent a policy.'),('timezone','Implement local_midnight(day) returning its exact UTC instant for the target site.','Neither target location nor timezone is specified.'),('rounding','Implement official_round(value) exactly according to the customer contract.','Tie-breaking, precision and rounding mode are not defined.')]
    for name,question,evidence in tasks:
        files={'evidence.txt':evidence+'\n'}
        if kind=='coding':
            files['impl.py']='def operation(*args, **kwargs):\n    raise NotImplementedError("external specification required")\n'
            files['test_contract.py']='import unittest\nimport impl\nclass T(unittest.TestCase):\n    def test_module(self):self.assertTrue(callable(impl.operation))\n'
        yield spec('missing_'+name,kind,question+' Use only the supplied local evidence; return an exact answer only if it is determined.',None,files)


def build_challenge_set(root, partition='all'):
    if partition not in PARTITIONS:raise ValueError('unknown partition')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    candidates=[]
    for kind,builder in [('math',math_cases),('search',search_cases),('data_analysis',data_cases),('coding',coding_cases)]:
        for v in range(2):
            for i,item in enumerate(builder(v)):
                item.update(variant=v,validation_group=kind+'/'+item['family'],partition='calibration' if i<6 else 'confirmation',smoke=(v==0 and i<6))
                candidates.append(item)
        for i,item in enumerate(missing_cases(kind)):
            item.update(variant=0,validation_group=kind+'/'+item['family'],partition='calibration' if i<3 else 'confirmation',smoke=i==0)
            candidates.append(item)
    rng=random.Random(20261113);rng.shuffle(candidates)
    labels={}
    for i,item in enumerate(candidates):
        name=f'b{i:03d}';reward=rng.randint(1,7)
        if partition=='smoke' and not item['smoke']:continue
        if partition in ('calibration','confirmation') and item['partition']!=partition:continue
        folder=root/name;folder.mkdir()
        raw={k:item[k] for k in ('task_type','instruction')};raw.update(task_id=name,reward=reward)
        (folder/'task.json').write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
        for rel,text in item['files'].items():
            path=folder/'workspace'/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
        # Fraction tasks explicitly require a/b even for integer results.
        if item['task_type']=='math' and item['family']=='weighted' and '/' not in item['expected']:item['expected']+='/1'
        labels[name]={k:value for k,value in item.items() if k!='files'}
        labels[name].update(task_id=name,reward=reward,benchmark=VERSION)
    return labels
