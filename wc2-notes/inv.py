import ast, sys
for f in sys.argv[1:]:
    t = ast.parse(open(f).read())
    for n in ast.walk(t):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, 'id', '') == 'check':
                    kw = {k.arg: k.value for k in d.keywords}
                    leaves = [ast.literal_eval(e) for e in kw['leaves'].elts] if 'leaves' in kw else []
                    s = kw.get('sentence')
                    try: sent = ast.literal_eval(s)
                    except Exception:
                        sent = ''.join(ast.literal_eval(p) for p in s.values) if isinstance(s, ast.JoinedStr) else ''
                    print(f.split('/')[-1], n.name, leaves); print('   ', sent[:600])
