import subprocess,time,json
end=time.time()+520
while time.time()<end:
    out=[]
    for n in (586,587):
        d=json.loads(subprocess.run(["gh","pr","view",str(n),"--repo","rpsj2230/Verz-OS-v2.0","--json","state,mergeable,headRefOid,statusCheckRollup,autoMergeRequest"],capture_output=True,text=True).stdout)
        cs=d["statusCheckRollup"]
        out.append((n,d["state"],d["mergeable"],d["headRefOid"][:8],len(cs),sum(c.get("status")!="COMPLETED" for c in cs),[c["name"] for c in cs if c.get("conclusion")=="FAILURE"],d["autoMergeRequest"] is not None))
    if all(o[5]==0 for o in out) or any(o[6] for o in out): break
    time.sleep(45)
for o in out: print(*o)
