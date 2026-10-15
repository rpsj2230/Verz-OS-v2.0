from pathlib import Path

from brain.ops.mutation import Mutation, verify

REPORT = "src/brain/ops/automation_report.py"
CHECKS = "src/brain/ops/acceptance_checks_automation_canvas.py"
SCRIPT = "ops/deploy/overlays/automation.observe.sh"
OVERLAYS = "src/brain/ops/overlays.py"
T = (
    "tests/unit/test_automation_report.py",
    "tests/unit/test_automation_observe.py",
    "tests/unit/test_acceptance_automation_canvas.py",
)


def m(label: str, path: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=path, before=before, after=after, tests=T)


mutations = [
    m("a foreign credential name is allowed", REPORT, "    if foreign:\n        found.append(Gap.FOREIGN_CREDENTIAL)", "    if False:\n        found.append(Gap.FOREIGN_CREDENTIAL)"),
    m("an unread connection count is allowed", REPORT, "facts.connection_strings is None or facts.connection_strings > 0", "facts.connection_strings is not None and facts.connection_strings > 0"),
    m("one connection string is allowed", REPORT, "facts.connection_strings > 0", "facts.connection_strings > 1"),
    m("an application variable is allowed", REPORT, "if any(name.startswith(APPLICATION_NAME_PREFIXES) for name in facts.env_names):\n        found.append(Gap.APPLICATION_VARIABLE)", "if False:\n        found.append(Gap.APPLICATION_VARIABLE)"),
    m("the canvas need not sit on its own network", REPORT, "if not canvas_ok or not any(one.endswith(SANDBOX_NETWORK_SUFFIX) for one in facts.networks):", "if not canvas_ok:"),
    m("a canvas on no network passes", REPORT, "canvas_ok = bool(facts.networks) and all(", "canvas_ok = all("),
    m("a proxy on no network passes", REPORT, "proxy_ok = bool(facts.proxy_networks) and all(", "proxy_ok = all("),
    m("one default route is allowed", REPORT, "elif facts.default_routes > 0:", "elif facts.default_routes > 1:"),
    m("an unread route count is allowed", REPORT, "    if facts.default_routes is None:\n        found.append(Gap.ROUTES_UNKNOWN)", "    if False:\n        found.append(Gap.ROUTES_UNKNOWN)"),
    m("an extra allowed host is allowed", REPORT, "if sorted(facts.allowlist) != sorted(EGRESS_ALLOWLIST):", "if not set(EGRESS_ALLOWLIST) <= set(facts.allowlist):"),
    m("a missing allowed host is allowed", REPORT, "if sorted(facts.allowlist) != sorted(EGRESS_ALLOWLIST):", "if not set(facts.allowlist) <= set(EGRESS_ALLOWLIST):"),
    m("a proxy that answers 200 is a refusal", REPORT, "if _status(facts.probe) != REFUSED_STATUS:", "if _status(facts.probe) is None:"),
    m("the refusal status is another", REPORT, "REFUSED_STATUS: Final = 403", "REFUSED_STATUS: Final = 407"),
    m("the vault's token is allowed through the credential rule", REPORT, '    {"AP_POSTGRES_PASSWORD", "AP_ENCRYPTION_KEY", "AP_JWT_SECRET"}', '    {"AP_POSTGRES_PASSWORD", "AP_ENCRYPTION_KEY", "AP_JWT_SECRET", "VAULT_TOKEN"}'),
    m("a value is accepted in a name line", REPORT, 'if not value.replace("_", "a").isalnum():', "if False:"),
    m("a report from another release is judged", REPORT, 'if not isinstance(value, Mapping) or value.get("commit") != commit:', "if not isinstance(value, Mapping):"),
    m("a boolean is a count", REPORT, "return found if isinstance(found, int) and not isinstance(found, bool) else None", "return found if isinstance(found, int) else None"),
    m("a line of an unknown kind is kept", REPORT, '            case _:\n                msg = f"a report line has a kind nothing reads', '            case "never":\n                msg = f"a report line has a kind nothing reads'),
    m("a failed keep exits zero", REPORT, '        print(f"SAY the canvas\'s facts were not kept: {describe(error)}")\n        return 1', '        print(f"SAY the canvas\'s facts were not kept: {describe(error)}")\n        return 0'),
    m("a canvas that is not named is judged", CHECKS, "    if not _switched_on():\n        raise CheckNotRunError(NO_CANVAS_HERE)\n    seen = await _services_reported(h)", "    if False:\n        raise CheckNotRunError(NO_CANVAS_HERE)\n    seen = await _services_reported(h)"),
    m("an unhealthy service is running", CHECKS, '(seen[name].state, seen[name].health) != ("running", "healthy")', 'seen[name].state != "running"'),
    m("a service over its budget is held", CHECKS, "if seen[name].limit_mib != component(name).memory_mib", "if seen[name].limit_mib < component(name).memory_mib"),
    m("a service with no limit is held", CHECKS, "if seen[name].limit_mib != component(name).memory_mib", "if 0 < seen[name].limit_mib != component(name).memory_mib"),
    m("an unread route count passes the check", CHECKS, "    if Gap.ROUTES_UNKNOWN in kinds:\n        raise CheckFailedError(THE_CANVAS_ROUTES_WERE_NOT_READ)", "    if False:\n        raise CheckFailedError(THE_CANVAS_ROUTES_WERE_NOT_READ)"),
    m("a canvas the setting does not name may run", CHECKS, "    elif present:\n        raise CheckFailedError(THE_CANVAS_RUNS_AND_IS_NOT_NAMED)", "    elif False:\n        raise CheckFailedError(THE_CANVAS_RUNS_AND_IS_NOT_NAMED)"),
    m("a canvas the setting names may be stopped", CHECKS, '        if any(name not in seen or seen[name].state != "running" for name in names):', "        if False:"),
    m("the canvas overlay runs no step", OVERLAYS, '        after=("automation.observe.sh",),\n', ""),
    m("a connection scheme is not counted", SCRIPT, "postgresql\\+psycopg|redis|rediss|amqp|mongodb", "postgresql\\+psycopg|redis|amqp|mongodb"),
    m("a default route is not counted", SCRIPT, '$2 == "00000000"', '$2 == "11111111"'),
    m("an unread routing table is zero", SCRIPT, 'END { if (seen) printf "routes|%d\\n", n + 0; else print "routes|unknown" }', 'END { printf "routes|%d\\n", n + 0 }'),
    m("a value leaves with its name", SCRIPT, "s/^\\([A-Za-z_][A-Za-z0-9_]*\\)=.*$/env|\\1/p", "s/^\\([A-Za-z_][A-Za-z0-9_]*=.*\\)$/env|\\1/p"),
    m("the probe keeps its carriage return", SCRIPT, "| tr -d '\\r' ||", "||"),
    m("a canvas with a missing proxy is reported", SCRIPT, 'if [ -z "$canvas" ] || [ -z "$proxy" ]; then', 'if [ -z "$canvas" ] && [ -z "$proxy" ]; then'),
    m("a failed hand-over exits zero", SCRIPT, 'exit "$code"', "exit 0"),
]

report = verify(
    mutations,
    repo=Path("."),
    carry=(
        "src/brain/ops/automation_report.py",
        "src/brain/ops/acceptance_checks_automation_canvas.py",
        "ops/deploy/overlays/automation.observe.sh",
        "src/brain/ops/automation.py",
        "src/brain/ops/overlays.py",
        ".dockerignore",
        "tests/unit/test_automation_report.py",
        "tests/unit/test_automation_observe.py",
        "tests/unit/test_acceptance_automation_canvas.py",
    ),
)
print(report.table())
print("SURVIVORS:", [s.label for s in report.survivors])
