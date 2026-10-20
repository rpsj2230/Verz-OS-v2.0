import sys,re
from brain.ops.acceptance import registered
pat=re.compile(sys.argv[1],re.I)
for c in registered():
    if pat.search(c.sentence) or pat.search(c.name):
        print(c.name,'|',','.join(c.leaves),'|',c.sentence[:200].replace('\n',' '));print()
