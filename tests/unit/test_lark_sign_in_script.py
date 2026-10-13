"""The script that gives an already imported realm Sign in with Lark agrees with the realm file.

Task ids: M1.1.8
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from brain.identity.brokering import LINK_FLOW_ALIAS
from brain.identity.lark_sign_in import ALIAS

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "keycloak" / "lark-sign-in.sh"
REALM = REPO / "ops" / "keycloak" / "realm-export.json"


def assigned(name: str) -> str:
    found = re.search(rf'^{name}="([^"]*)"$', SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert found is not None, name
    return found.group(1)


def test_the_script_adds_the_flow_and_the_alias_the_application_and_the_realm_name() -> None:
    """Delete this and the script can create a flow under one name while the entry the
    application prints names another, which Keycloak refuses at the first sign-in."""
    assert assigned("FLOW") == LINK_FLOW_ALIAS
    assert assigned("ALIAS") == ALIAS


def test_the_script_makes_the_two_steps_the_realm_file_carries_and_requires_both() -> None:
    """Delete this and an already imported realm can end with a different flow from a fresh one:
    a step missing, or one that is not required, which lets a stranger through or locks everybody
    out."""
    realm = json.loads(REALM.read_text(encoding="utf-8"))
    [flow] = [one for one in realm["authenticationFlows"] if one["alias"] == LINK_FLOW_ALIAS]
    steps = [one["authenticator"] for one in flow["authenticationExecutions"]]
    text = SCRIPT.read_text(encoding="utf-8")

    assert re.search(r"for step in ([a-z -]+); do", text) is not None
    made = re.search(r"for step in ([a-z -]+); do", text)
    assert made is not None and made.group(1).split() == steps
    expected = json.dumps([[step, "REQUIRED"] for step in steps], separators=(",", ":"))
    assert f"'{expected}'" in text


def test_the_script_is_valid_shell_and_never_puts_the_password_on_a_command_line() -> None:
    """Delete this and a typo in the script is found by the person running it against their
    sign-in service, or the administrator's password lands in the process list."""
    checked = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert checked.returncode == 0, checked.stderr
    text = SCRIPT.read_text(encoding="utf-8")
    assert "printf '%s' \"$KEYCLOAK_ADMIN_PASSWORD\" |" in text
    assert "password@-" in text
    assert re.search(r'password=\$|password="\$', text) is None
