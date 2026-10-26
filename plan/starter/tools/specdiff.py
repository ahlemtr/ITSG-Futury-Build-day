import re, difflib, json, sys
sec_re=re.compile(r'^\s*(\d(?:\.\d+)+)\s+(Datensatz|Datenbaustein)\s+(D[A-Z]{3})\b')
row_re=re.compile(r'^\s*\d{3}\s*[-–]\s+\d{2,3}\s+(an|n|AN|N)\s+[MmKk]\s+(\S+)')
def norm(path):
    out=[]; blk=None; fld=None; body=False
    for l in open(path,encoding='utf-8').read().split('\n'):
        s=' '.join(l.split())
        if not s: continue
        if re.match(r'^Stand: \d',s) or re.match(r'^Seite \d+ von',s): continue
        if s.startswith('Datensatz DSLW – Datensatz Leistungswesen') and body and not sec_re.match(l): continue
        if re.match(r'^Datenbaustein D[A-Z]{3}',s) and not sec_re.match(l): continue
        m=sec_re.match(l)
        if m: blk=m.group(3); fld=None; body=True
        r=row_re.match(l)
        if r: fld=r.group(2)
        out.append((s,blk,fld))
    return out
A=norm('vb133.txt'); B=norm('vb.txt')
sm=difflib.SequenceMatcher(a=[x[0] for x in A],b=[x[0] for x in B],autojunk=False)
changes=[]
for tag,i1,i2,j1,j2 in sm.get_opcodes():
    if tag=='equal': continue
    ctx=B[j1] if j1<len(B) else B[-1]
    changes.append(dict(tag=tag,block=ctx[1],field=ctx[2],old=[x[0] for x in A[i1:i2]],new=[x[0] for x in B[j1:j2]]))
json.dump(changes,open('diff_13.3_13.4.json','w'),ensure_ascii=False,indent=1)
print(len(changes))
for c in changes:
    if c['block'] is None: continue
    o=' / '.join(c['old'])[:300]; n=' / '.join(c['new'])[:300]
    print(f"--- [{c['block']} {c['field']}] {c['tag']}\n  OLD: {o}\n  NEW: {n}")
