import sys
from brain.ops.acceptance import check_modules, registered
leaves=set(sys.argv[1:])
for m in check_modules():
    for c in registered((m,)):
        if leaves & set(c.leaves):
            print(m, c.name, sorted(leaves & set(c.leaves)))
