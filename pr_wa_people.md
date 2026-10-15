Five install checks for the people side of the staff list, so the leaves they name can be shown working on the owner's install: Sync now (M1.10.2), what People says about each person the list names (M1.6.13), adding a work email and the join it makes (M1.10.4, M1.10.5) and departments managed on People (M1.6.19).

- Each check calls the route its page calls, as a reserved person, in the harness's rolled-back transaction. Sync now stops at the worker's door and says so; checks that need a chosen staff source say NOT_RUN in a literal sentence where there is none, rather than assuming the empty state.
- Product change, small: the question both the people step and the accounts step asked inline is now `departments_from.the_list_places_people`, which the departments check asks of the product instead of a copy.
- `docs/proof-sweep-holds.json`: M1.6.13, M1.10.4, M1.10.5 and M1.6.19 are held with their siblings' reason (each passes against a roster the check made). M1.10.2 is not.
- Mutation, three rows, all caught (table in the commit message). No migration, no route or screen change, so no console-audit regeneration.

Verified locally: ruff, ruff format, mypy --platform linux, traceability, compatibility, tests/invariants (1489 passed), the touched unit files and test_acceptance.py on PostgreSQL at head.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
