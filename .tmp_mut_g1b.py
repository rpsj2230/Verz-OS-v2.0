from pathlib import Path

from brain.ops.mutation import Mutation, verify

REV = "src/brain/ops/person_token_revoker.py"
OAU = "src/brain/connectors/oauth.py"
GW = "src/brain/connectors/google_workspace.py"
MAR = "src/brain/member_accounts_routes.py"
CR = "src/brain/connector_routes.py"
MR = "src/brain/mine_routes.py"
T_REV = ("tests/unit/test_person_token_revoker.py",)
T_RT = ("tests/unit/test_member_accounts.py", "tests/unit/test_connector_consent_routes.py")
T_MINE = ("tests/unit/test_mine_routes.py",)

M = [
    Mutation("no poster reads as revoked", REV,
             "        if poster is None:\n            return False",
             "        if poster is None:\n            return True", T_REV),
    Mutation("a timeout is not a failure", REV,
             "if answer.timed_out or answer.connection_failed or answer.status is None:",
             "if answer.status is None:", T_REV),
    Mutation("not-valid is recognised on any status", REV,
             "    if answer.status != 400:\n        return False", "    if False:\n        return False", T_REV),
    Mutation("any source can be disconnected", MAR,
             "if consent is None or consent.kind is not ConsentKind.PERSON:", "if consent is None:", T_RT),
    Mutation("evidence kept for lines with none", MR,
             "        for one in told.items\n        if one.evidence\n    }", "        for one in told.items\n    }", T_MINE),
]

report = verify(M, repo=Path('.'), carry=())
print(report.table())
print('SURVIVORS:', [s.label for s in report.survivors])
