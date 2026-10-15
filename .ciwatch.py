import json, subprocess, time, sys
prs = [586, 587, 591, 595]
def state(n):
    out = subprocess.run(["gh","pr","view",str(n),"--repo","rpsj2230/Verz-OS-v2.0","--json","statusCheckRollup,headRefOid"],capture_output=True,text=True).stdout
    d = json.loads(out)
    cs = d["statusCheckRollup"]
    pend = [c["name"] for c in cs if c.get("status") != "COMPLETED"]
    fail = [c["name"] for c in cs if c.get("conclusion") in ("FAILURE","CANCELLED","TIMED_OUT")]
    return d["headRefOid"][:8], len(cs), pend, fail
end = time.time() + 540
while time.time() < end:
    s = {n: state(n) for n in prs}
    if all(not s[n][2] for n in prs): break
    time.sleep(30)
for n in prs:
    h, total, pend, fail = s[n]
    print(n, h, "checks", total, "pending", len(pend), "failed", fail)
