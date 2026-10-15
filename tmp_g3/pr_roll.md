**Three install-proof leaves get their checks: M10.7.3 (channels), M11.8.13 (connectors area), and honest roll-ups for M1.8.5 and M11.8.3 that name what no check shows yet. M1.6.18 and M1.1.9 each get a check that cannot run and says why.**

## Why
Each leaf is a sentence of clauses. Several clauses already have a check written for a narrower leaf; none names the composite, so no install result could close it.

- `acceptance_checks_channels_roll_up` (key 1290): **M10.7.3**. Fifteen clauses, each mapped to the checks that show it (Lark, Slack, Teams, WhatsApp, Telegram, email, the REST API, the web at the narrower reach, progress streamed, unbound sender, bad signature, retry once, approval notice, second channel, agent not enabled). It reads this run's earlier results and asks nothing of the install. Held in `proof-sweep-holds.json`: every channel check passes against secrets the check made, until the owner's own account is connected (item 126).
- `acceptance_checks_connectors_area` (key 1215): **M11.8.13**. Passes only when every Connectors requirement in the register has a newest check recorded by a person that passed; not run while one has none; failed while a newest one failed. Same three outcomes as the sibling areas' checks in #495/the proof train, restated for one area so it does not wait on a branch that has not landed.
- `acceptance_checks_proof_gaps` (key 1291): roll-ups for **M1.8.5** and **M11.8.3** that name, in the reason, the clauses with no check today (identity: signing in through the identity provider, session idle and absolute limits, an account bound to nobody told once; live reading: a question spanning many records, document embeddings with no outbound call). `tests/unit/test_acceptance_proof_gaps.py` pins that list, so a clause cannot be written out to make a roll-up pass. Plus two checks that cannot run and say why: **M1.6.18** (Forgot password needs a mailbox a person reads; no check makes a real account at the owner's sign-in service) and **M1.1.9** (a real Lark account and the real sign-in).

## Verification
- New tests pass against a fresh PostgreSQL: roll-up 5, proof gaps 4, connectors area 6; `test_acceptance.py` (including the install-from-empty run) 25 passed; `test_acceptance_roll_up.py` passed.
- ruff format and check, `mypy --platform linux` clean. No migrations.

## Not done
M11.8.3 cannot close until M7.3.3 (the local inference server, item 25) and a question shape that filters many records exist: both are named in its reason.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
