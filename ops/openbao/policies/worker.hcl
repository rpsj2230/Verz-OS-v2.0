# What the background worker may do with the secrets vault.
#
# Task ids: M31.3.2.2, M27.8.12, M42.6.2, M42.6.5
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

# The key a connected source's vendor issued, read to read that source and for nothing else. The
# worker is the one process that runs a connector (brain.ops.connector_sync_run), so it is the one
# policy that reads these; the application writes a key when an administrator connects a source and
# reads only its metadata. Read and nothing more: no create, update or delete, because a process
# nobody watches must not be able to replace the key a source checks, and no metadata, because the
# worker has no screen to tell.
#
# One path segment for every source rather than a rule per source, and that is not the wildcard the
# connectors/creds rules above refuse. Which sources are connected is decided in the console by an
# administrator holding admin:connector over each, recorded in ops.connector_connection, and a rule
# per source would mean every connection waits for somebody with a policy-writing token to reload
# this file, which is the token the first-run steps revoke. The worker reads a key only through the
# reference a live connection's own manifest names (brain.ops.connectable.key_reference), so a slot
# with no connection is never asked for.
path "connector_keys/data/+" {
  capabilities = ["read"]
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
