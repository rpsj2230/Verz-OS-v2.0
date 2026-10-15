import subprocess,time,json
end=time.time()+500
while time.time()<end:
    d=json.loads(subprocess.run(["gh","pr","view","595","--repo","rpsj2230/Verz-OS-v2.0","--json","state,mergeable,headRefOid,statusCheckRollup"],capture_output=True,text=True).stdout)
    cs=d["statusCheckRollup"]
    fail=[c["name"] for c in cs if c.get("conclusion")=="FAILURE"]
    if d["state"]=="MERGED" or fail: break
    time.sleep(45)
print(d["state"],d["mergeable"],d["headRefOid"][:8],len(cs),"pending",sum(c.get("status")!="COMPLETED" for c in cs),fail)
