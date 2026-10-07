## What

M11.8.8, live connector answers, in two halves.

- **The automated half is a regression over a helpdesk made up for the run:** `acceptance_checks_live_answers` (CHECK_ORDER 425). It checks that:
  - every connector the console offers is keyed by reference to its own vault slot, and scoped;
  - the made-up helpdesk is connected from its form, with its key kept by the product's keeper in a vault the check holds, and is read with that key;
  - a person's question about its open ticket on `/answer` cites the ticket id, the field read live, Freshdesk, and when it was read;
  - a bound agent answers, and an unbound agent is told what a missing ticket tells it.
- **The live half is the owner's recorded walk-through**, item 91 check 14, on Install > Requirement checks. A check never reads the company's own tickets, because `A_CHECK_GRANTS_NOBODY_OUTSIDE_ITS_DEPARTMENTS` stays whole.
  - The Connectors area of the Requirement checks route now names M11.8.8 beside M11.8.13 (`ALSO_PROVED_BY`, `also_proves`, and the reason `A_LIVE_HALF_IS_PROVED_BY_A_PERSON`).
  - A test holds that, and holds that the register's Connectors rows name the leaf as their proof.

## Proof

- **Breaks:** three product breaks each fail the check with its own sentence: no citations, citations with no read time, and a run at the caller's reach whatever the agent.
- **Tests:** 1546 passed on a fresh database, across tests/invariants, test_acceptance_live_answers, test_acceptance, test_acceptance_connectable and test_requirement_check_routes.
- **Gates:** ruff, format, mypy (`--platform linux`) all exit 0.

Mutations (`brain.ops.mutation.verify`, 3 of 3 caught):

| Mutation | Outcome | Caught by |
|---|---|---|
| a citation carries the instant its field was read (product) | caught | the real-database run and the `undated` break |
| the check refuses an answer that does not cite the read time | caught | the `undated` break |
| the Connectors area names the leaf its recorded checks prove | caught | test_the_connectors_area_names_the_live_answers_leaf_its_recorded_checks_prove |

## Not done

- **"A client's open tickets" is asked as one open ticket.** No question shape on Ask covers many records yet; the survey and `acceptance_checks_sources` say so.
- **The console shows nothing new.** It does not display the area's leaf today. The API carries it, and the screen can show it later.

Reused:
- `acceptance_checks_connectable`: `_from_the_console`, `_answering`, `_two_agents`, `_served`, `_on_ask`, `_asked` and `_prose`.
- The framework check's `_form` and `_Vault`.
- `acceptance_checks_sources`' helpdesk.
- `Credentials` and `StoredCredentialWrites`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
