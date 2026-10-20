## What

This PR adds an install check for M11.8.5: every write a connector can make is a declared tool, it stays off until its key is given, and turning it on is audited. The write half of the connector contract already exists (Cloudflare's DNS changes, #298). Until now it was checked only as Cloudflare.

`a_connector_write_is_a_declared_tool_off_until_its_key_is_given` is a third check in `acceptance_checks_cloudflare`. It covers three things:
- **Every write is a declared tool.** Each write grant a shipped connector declares names tools that its own module declares, with a side effect other than none, under the connector's own name. Cloudflare's DNS changes are the anchor, so a discovery that finds nothing fails.
- **Off until its key is given.** A connection given only its read key holds no key for the grant.
- **Turning it on is audited.** The grant's key is given through `connector_routes.keep_credential`, the Connectors route's own keeper. The key is kept in the grant's slot, and a `credential` ledger entry is appended under that slot, naming the person who gave it. No part of the key appears in the ledger or in any table.

The second Cloudflare check also names M11.8.5, because it proves the rest of the leaf: a write that is on runs only as an approved prepared action, sent once with the grant's key, read back with the read key, and told at the requester's reach.

## Proof

- test_acceptance_cloudflare: 15 passed on a fresh database. tests/invariants and test_acceptance.py: 1523 passed in the same run.
- The broken-path test gains two breaks: the write's tool declared as changing nothing, and the key kept with its record lost. Each fails the new check with its own sentence.
- ruff, format, mypy (`--platform linux`) and traceability all exit 0.

Mutations (`brain.ops.mutation.verify`, 2 of 2 caught):

| Mutation | Outcome | Caught by |
|---|---|---|
| a write declared as changing nothing is refused | caught | test_the_cloudflare_checks_fail_where_the_path_is_broken[...-tool-...] |
| turning a write on must leave a ledger entry by its giver | caught | test_the_cloudflare_checks_fail_where_the_path_is_broken[...-unrecorded-...] |

## Not done

- **Turning a write off is removing its key.** Removing the grant's key from its slot is the off switch, and an approval then tells the approver the install has not allowed the write. No separate switch-off act is built, as the coordinator decided.

Reused: `keep_credential`, `Credentials`, `StoredCredentialWrites` and its 0054 ledger trigger, the framework check's `_Vault`, and Cloudflare's `_connected`, `DNS_CHANGES` and `DNS_CHANGE_TOOL`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
