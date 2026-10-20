## What

M11.8.10, a connector write proved on an install, as a second check in `acceptance_freshdesk_reply`. **Stacked on #372 (and #368 under it). Base is M11/w2-freshdesk-reply and auto-merge is off**, because it lands behind the migration train.

The check reaches #372's approved reply by the same path. The setup is now one helper that both checks use. Then it does four things:
1. **Off.** It runs the worker with nothing kept for the reply grant. Nothing is sent, and the approval stands.
2. **Turned on by an administrator.** The reply key is given through `connector_routes.keep_credential`, the Connectors route's own keeper. The check finds the `credential` ledger entry by that administrator.
3. **On.** The worker leases the grant's key from the vault the keeper wrote. It posts the reply once with that key, at the requester's reach, and reads it back before reporting done. A third run sends nothing.
4. **Announced.** An `operation.settled` event goes through the outbox's own `claim_due` and `dispatch_due` to a receiver that refuses the first attempt. On the retry it is delivered with the same bytes both times. Each attempt is signed, and the check verifies the signature as a receiver does, with the inbound `brain.channels.webhook.sign`, not the sender's own function.

## Proof

- **Breaks:** four product breaks each fail the new check with its own sentence:
  - the key kept with its record lost;
  - the write sent with the read key's slot;
  - the event signed over bytes other than those it sends;
  - a refused delivery never tried again.
- **Tests:** 1678 passed on a fresh database, across tests/invariants, test_acceptance_freshdesk_reply, test_acceptance, test_freshdesk_reply, test_approved_runs, test_outbox_store, test_outbox and test_webhook_delivery.
- **Gates:** ruff, format, mypy (`--platform linux`) and traceability all exit 0.

Mutations (`brain.ops.mutation.verify`):

| Mutation | Outcome | Caught by |
|---|---|---|
| turning the write on must leave the administrator's ledger entry | caught | the `unrecorded` break |
| each delivery must verify as a receiver checks it | caught | the `unsigned` break |
| the event must be delivered on a retry (request count dropped) | SURVIVED, equivalent | none |

The survivor is equivalent. The receiver refuses exactly the first request, so a delivery that reaches DELIVERED within the two claims has been sent twice. Every break that loses the retry leaves the delivery pending or exhausted, and the state condition refuses both.

## Not done

- **What only a real receiver proves:** that it verifies the signature and drops a second copy on the event id. That is the receiver's own to show.
- **Not proved on the owner's install.** Freshdesk is not connected there (item 128).

Reused:
- #372's `_Desk`, `_Lease`, `ConnectorWrites` and `run_approved`
- `keep_credential`, `Credentials` and `StoredCredentialWrites`
- the framework check's `_Vault`
- `outbox_store.register_subscriber`, `record_event`, `claim_due` and `dispatch_due`
- `brain.channels.webhook.sign`
- `_HeldLedger`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
