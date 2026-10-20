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
    Mutation("handle must name the person's own slot", REV,
             "if token_ref != self._reference.path:", "if False:", T_REV),
    Mutation("vendor failure no longer stops the removal", REV,
             "if not self._vendor_revoked(at):", "if False:", T_REV),
    Mutation("no endpoint declared reads as not revoked", REV,
             "        if not self._consent.revoke_url:\n            return True",
             "        if not self._consent.revoke_url:\n            return False", T_REV),
    Mutation("no poster reads as revoked", REV,
             "        if poster is None:\n            return False",
             "        if poster is None:\n            return True", T_REV),
    Mutation("a refused address reads as revoked", REV,
             "        except (ConnectorContractError, UnsafeAddressError):\n            return False",
             "        except (ConnectorContractError, UnsafeAddressError):\n            return True", T_REV),
    Mutation("a timeout is not a failure", REV,
             "if answer.timed_out or answer.connection_failed or answer.status is None:",
             "if answer.status is None:", T_REV),
    Mutation("any answer is a revocation", REV,
             "return 200 <= answer.status < 300 or _already_gone(answer)", "return True", T_REV),
    Mutation("not-valid is recognised on any status", REV,
             "    if answer.status != 400:\n        return False", "    if False:\n        return False", T_REV),
    Mutation("any 400 JSON is already gone", REV,
             'return isinstance(parsed, dict) and parsed.get("error") in _NO_LONGER_VALID',
             "return isinstance(parsed, dict)", T_REV),
    Mutation("invalid_request counts as gone", REV,
             'frozenset({"invalid_token", "invalid_grant"})',
             'frozenset({"invalid_token", "invalid_grant", "invalid_request"})', T_REV),
    Mutation("a vault refusal reads as removed", REV,
             'log.warning("the vault would not remove a revoked token", source=self._connector)\n            return False',
             'log.warning("the vault would not remove a revoked token", source=self._connector)\n            return True', T_REV),
    Mutation("an unreadable token reads as revoked", REV,
             "        except SecretsUnavailableError:\n            return False\n        finally:",
             "        except SecretsUnavailableError:\n            return True\n        finally:", T_REV),
    Mutation("no endpoint builds a request anyway", OAU,
             "    if not consent.revoke_url:\n        return None", "    if False:\n        return None", T_REV),
    Mutation("revocation address need not be https", OAU,
             "        if self.revoke_url:\n            _https(self.revoke_url", "        if False:\n            _https(self.revoke_url", T_REV),
    Mutation("google revocation address", GW,
             'REVOKE_URL: Final = "https://oauth2.googleapis.com/revoke"',
             'REVOKE_URL: Final = "https://oauth2.googleapis.com/token"', T_REV),
    Mutation("any source can be disconnected", MAR,
             "if consent is None or consent.kind is not ConsentKind.PERSON:", "if consent is None:", T_RT),
    Mutation("nothing held still disconnects", MAR, "    if not held.held:", "    if False:", T_RT),
    Mutation("no revoker still proceeds", MAR, "    if revoker is None:", "    if False:", T_RT),
    Mutation("vendor claimed asked always", MAR,
             "asked_the_vendor = bool(consent.revoke_url)", "asked_the_vendor = True", T_RT),
    Mutation("another department's connection is inherited", CR,
             "if one is None or not department or department not in held:",
             "if one is None or not department:", T_RT),
    Mutation("a person's own source is inherited", CR,
             "        if one.oauth is not None and one.oauth.kind is ConsentKind.PERSON:\n            continue",
             "        if False:\n            continue", T_RT),
    Mutation("no records is an error not an empty list", CR,
             "    records = records_of(request)\n    if records is None:\n        return []\n    held =",
             "    records = records_of(request)\n    if False:\n        return []\n    held =", T_RT),
    Mutation("disconnect offered when not held", CR,
             "disconnectable=connected is True,", "disconnectable=True,", T_RT),
    Mutation("a department's connection is offered a disconnect", CR,
             "provenance=Provenance.DEPARTMENT.value,\n                disconnectable=False,",
             "provenance=Provenance.DEPARTMENT.value,\n                disconnectable=True,", T_RT),
    Mutation("evidence kept for lines with none", MR,
             "        for one in told.items\n        if one.evidence\n    }", "        for one in told.items\n    }", T_MINE),
    Mutation("an inferred line with no record says it was noticed", MR,
             "WHAT_WAS_NOTICED if one.memory_id in evidence else NO_RECORD_OF_WHY", "WHAT_WAS_NOTICED", T_MINE),
    Mutation("a stated line is given evidence", MR,
             "                    evidence=[],\n                    evidence_told=YOU_SAID_IT_YOURSELF,",
             '                    evidence=["x"],\n                    evidence_told=YOU_SAID_IT_YOURSELF,', T_MINE),
]

report = verify(M, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS:", [s.label for s in report.survivors])
