# What the background worker may do with the secrets vault.
#
# Task ids: M31.3.2.2, M31.3.2.3, M27.8.12, M42.6.2, M42.6.5, M5.4.7
#
# The worker runs scheduled and queued work, so its runs are longer than a request and
# nobody is watching them. Two differences from the application follow from that, and both
# are narrowing rather than widening.
#
# It may renew a lease, because a sync that legitimately runs for twenty minutes should
# extend rather than hold a one-hour lease from the start. It may NOT reach the connector
# credentials a person's question would use: a worker that can borrow any connector's key
# is a way to read anything on a schedule, with no person in the loop to notice.

path "database/creds/brain_worker" {
  capabilities = ["read"]
}

# Only the connectors a scheduled job is configured for, named one at a time. A wildcard
# here would make the worker the widest role in the system, which is the opposite of what a
# process nobody watches should be.
path "connectors/creds/lark_base" {
  capabilities = ["read"]
}

path "connectors/creds/laravel_readonly" {
  capabilities = ["read"]
}

# Webhook subscribers' signing secrets, read to sign a delivery and for nothing else. The worker is
# the one process that signs (brain.ops.webhook_delivery), so it is the one policy that reads
# these; the application writes them from the console and reads only their metadata. Read and
# nothing more: no create, update or delete, because a process nobody watches must not be able to
# replace the key every receiver checks. No metadata, because the worker has no screen to tell.
path "webhooks/data/+" {
  capabilities = ["read"]
}

# The four model providers' keys, read to probe a provider and for nothing else (M5.4.7). The
# worker's schedule runs the model health prober (brain.ops.model_probe_run) every minute, and a
# probe is an authenticated request, so without a key there is no probe and a dead provider stays in
# rotation until a person's question finds it. Named one at a time and never providers/data/+,
# because the same engine holds the mail relay's password at providers/mail_relay and the keys of
# providers added from the console, and the prober needs neither. Read and nothing more: a process
# nobody watches must not be able to replace the key every question is sent with. No metadata: the
# worker has no screen to tell. The key is kept in the worker's memory for a quarter of an hour and
# never enters its environment. A slot added to brain.ops.provider_keys.PROVIDER_SLOTS is added
# here too, and tests/unit/test_vault_policies.py holds the two lists equal.
path "providers/data/anthropic" {
  capabilities = ["read"]
}

path "providers/data/openai" {
  capabilities = ["read"]
}

path "providers/data/moonshot" {
  capabilities = ["read"]
}

path "providers/data/deepseek" {
  capabilities = ["read"]
}

# The key a connected source's vendor issued is NOT read under this policy. Until 2026-09-17 it was,
# on connector_keys/data/+, which made this token, renewed for as long as the worker runs, a standing
# read of every source's key. The worker now mints a run token per attempt against the connector-run
# token role, whose policy (connector-run.hcl) is the only one that reads a key, and revokes it when
# the attempt ends. See brain.ops.connector_lease.THE_WORKER_READS_A_KEY_ONLY_THROUGH_A_RUN_LEASE.
#
# Minting one is all this grants: the role fixes the policy, the TTL ceiling and no renewal, and a
# token role's allowed_policies is what lets a child carry a policy its parent does not. No other
# role, no auth/token/create without a role, and nothing under auth/token/roles, so the worker
# cannot widen the role it mints against.
path "auth/token/create/connector-run" {
  capabilities = ["create", "update"]
}

path "sys/leases/revoke" {
  capabilities = ["update"]
}

path "sys/leases/renew" {
  capabilities = ["update"]
}

# Its own token's standing, and its renewal. Granted here rather than left to the vault's default
# policy, which grants both today and which a token minted with -no-default-policy does not carry:
# a periodic token nothing renews lapses for good. Self only: renewing a token takes the token, so
# this reaches no other process's. See brain.ops.vault_renewal.RENEWAL_TAKES_THE_CREDENTIAL_SO_EACH_HOLDER_RENEWS_ITS_OWN.
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
