"""Hand-run mutation harness for the console: break one thing in this worktree, run the named test
file, report which tests failed, restore byte-identically and check the md5. Usage:
python3 mut.py <label> <file> <old> <new> <test file> [<test file> ...]
The old text is replaced once. Exits 2 when the pattern is missing.
"""
import hashlib, os, re, subprocess, sys

label, path, old, new, *tests = sys.argv[1:]
root = "/Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/w3-lists/console"
full = os.path.join(root, path)
before = open(full, "rb").read()
digest = hashlib.md5(before).hexdigest()
text = before.decode()
if old not in text:
    print(f"{label}: PATTERN NOT FOUND")
    sys.exit(2)
open(full, "w").write(text.replace(old, new, 1))
env = dict(os.environ, PATH="/opt/homebrew/bin:" + os.environ["PATH"], NODE_OPTIONS="--no-experimental-webstorage")
try:
    out = subprocess.run(["npx", "vitest", "run", *tests], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900).stdout
finally:
    open(full, "wb").write(before)
after = hashlib.md5(open(full, "rb").read()).hexdigest()
failed = sorted(set(re.findall(r" FAIL  (\S+) > (.*)", out)))
summary = re.findall(r"Tests\s+.*", out)
print(f"### {label}")
print(f"restored byte-identically: {digest == after}")
print("\n".join(f"  FAILED {f}: {n}" for f, n in failed[:6]) or "  SURVIVED (no test failed)")
print("  " + (summary[-1] if summary else "no summary"))
