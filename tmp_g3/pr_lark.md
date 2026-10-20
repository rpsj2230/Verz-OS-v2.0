**Sign in with Lark (M1.1.8), the product half.** Item 115 decided a second way in for a company whose staff list is Lark: a person on the list signs in with Lark and no password, as the account the staff sync already made for them. It ships **off**: nothing changes on any install until its owner sets it up (needs-rupash item 197).

## Why a bridge
Keycloak's generic OpenID Connect broker needs an ID token and a flat user document. Lark's token endpoint takes JSON and answers no ID token, and its user information is wrapped under `data`. `brokering.py` refused Lark for that reason. `brain.identity.lark_sign_in` is the pure translation, `brain.lark_sign_in_routes` is the one address (`POST /lark-sign-in/token`) Keycloak posts a returned code to, and `brokering.py` now emits the Lark entry from the install's own settings: Lark's own sign-in page, the bridge, the secret as the same vault reference Google and Microsoft use.

## What it guarantees
- **It never makes an account.** The entry's first-login flow (`brain link by work address`, added to `realm-export.json`) has Detect Existing Broker User and Automatically Set Existing User, both required, and no Create User If Unique and no email step. A person with no account is refused, a disabled leaver is refused by Keycloak, and nobody is sent an email.
- **The person is matched on the staff sync's own address function** (`lark_work_address`), so the address Keycloak is told is the address the account was made with.
- **The secret is forwarded and kept nowhere:** a canary test reads every response and log line. Every refusal is one fixed word that names nothing Lark said.
- **Off by default:** the route answers 404 on an install whose settings do not broker Lark. It sits outside the API prefix, so the rule that every route there authenticates keeps its two written exceptions, and it is out of the public schema. A per-minute cap is a backstop against anybody posting to it.
- **Ordinary, not strong, assurance:** Lark's sign-in carries no `amr`, so administration and approval still ask for password and second factor (DEF-06). Item 197 asks the owner to confirm.

## Also here
- `ops/keycloak/lark-sign-in.sh`: gives an already imported realm the flow and the entry, idempotent, read back (the owner's staging realm already exists, and Keycloak never re-imports).
- `docs/install/authentication.md` "Signing in with Lark"; needs-rupash items **197** (the steps and one question), **198** (going live with real systems, M38.4.2.x and M38.2.2.6, and the rule that recordings are refreshed for shape only) and **199** (the Maintenance Agent's sign-off criteria, M38.5.3).
- `acceptance_checks_lark_sign_in` (key 1210, M1.1.8): asks the application's own bridge, mounted as the application mounts it, on a recorded Lark. Not run, with a literal reason, on an install that does not broker Lark. Held in `proof-sweep-holds.json`: Keycloak's linking is shown only by the owner's own sign-in. M1.1.9 is deliberately not claimed here.

## Verification
- 30 + 20 + 3 + 5 new tests pass; the brokering, realm, configuration, routers, privileges, independence and invariants suites pass locally (1605 passed, 2 failed before the last fix: both mine, both fixed, `test_acceptance.py` 25 passed after).
- Mutations (3 of 3 caught): the exchange redeemed only for the broker's own return address, the client id check, and a non-Lark install having nothing at the address.
- ruff format and check, `mypy --platform linux` clean.

## Not done, said plainly
**Nothing has run against Lark or Keycloak.** The unsigned ID token, `disableNonce`, `disableUserInfo` and how Keycloak's flow answers a stranger are from Keycloak's documented behaviour and its source as I recall it, and the owner's own first sign-in is what shows them. Lark's scope names for a user's own grant are the staff sync's two email scopes, unverified for this use.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
