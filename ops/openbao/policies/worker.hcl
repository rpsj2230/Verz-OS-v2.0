# What the background worker may do with the secrets vault.
#
# Task ids: M31.3.2.2, M27.8.12
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

path "sys/leases/revoke" {
  capabilities = ["update"]
}

path "sys/leases/renew" {
  capabilities = ["update"]
}
