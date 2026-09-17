# What the application may do with the secrets vault.
#
# Task ids: M31.3.2.2, M27.8.7, M27.8.12, M42.6.5, M42.6.2
#
# The application answers questions. It borrows connector credentials for the length of one
# request and gives them back, which is why most rules below are about *creating and
# revoking a lease*.
#
# It cannot read a connector's stored secret at all. That is the point of the split: a role
# that can read `connectors/xero` holds Xero's key for as long as the process lives, and
# every leak after that is a copy of a key nobody can rotate without noticing what broke.

# Ask for a lease against a dynamic role. The credential the vault mints is scoped and
# expires; the application never sees the underlying key.
path "database/creds/brain_app" {
  capabilities = ["read"]
}

path "connectors/creds/+" {
  capabilities = ["read"]
}

# Give a lease back. Explicitly granted rather than assumed: a role that can create leases
# and cannot revoke them accumulates live credentials until they expire, and the whole
# design rests on revocation happening at the end of a run.
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

# Model provider keys, the one category nothing can lease. See brain.ops.provider_keys and
# brain.ops.credentials, which argue both grants at length.
#
# create and update, so an administrator can put a key in from the console and the setup
# wizard can keep the one it asked for, instead of somebody at the server holding a root
# token. read, because the process that uses a key reads it once at start into its own
# environment, where the provider SDK finds it; without it a key written here would work
# until the first restart and never again. One path segment and one engine, `providers`,
# so nothing in `connectors/` is writable or readable this way. No delete and no list: a
# slot is replaced, never removed from here, and the slots are a closed list in the code.
# The mail relay's password is kept here too, at providers/mail_relay, for the same reasons: a
# relay's operator issues it, nothing can mint one per message, and the application is the process
# that sends mail with it. See brain.ops.mail.A_RELAY_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL.
path "providers/data/+" {
  capabilities = ["create", "update", "read"]
}

# When a slot was written, and whether its current version still exists. Metadata carries
# version numbers, times and deletion marks and no field of the secret, which is what lets
# the console say a key is held without reading it back. Read only: update on metadata sets
# how many versions are kept and when they are deleted, which is a way to erase a key's
# history, and custom metadata is not needed for anything here.
path "providers/metadata/+" {
  capabilities = ["read"]
}

# Webhook subscribers' signing secrets, the second thing nothing can lease: the receiver checks
# every delivery against the same value, so it is stored and replaced whole. See
# brain.ops.openbao.A_SIGNING_KEY_EVERY_RECEIVER_CHECKS_CANNOT_BE_MINTED and brain.ops.webhook_admin.
#
# create and update, so an administrator registers a subscriber and rotates its secret from the
# console. No read: the application writes these and never signs with them. The worker delivers,
# and reads them under its own policy (worker.hcl). Metadata read only, for the reason given above
# for providers: it is how the console says a secret is held without reading it back.
path "webhooks/data/+" {
  capabilities = ["create", "update"]
}

path "webhooks/metadata/+" {
  capabilities = ["read"]
}

# The key a connected source's vendor issued, the third thing nothing can lease. See
# brain.ops.openbao.A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT and
# brain.ops.connector_admin.
#
# create and update, so an administrator holding admin:connector connects a source from the
# console and the key goes straight into its slot, one slot per source. No read: this process
# answers questions and runs no connector, so a read here would be a standing copy of every
# source's key in the process that talks to a model. Whatever runs a connector will read under its
# own policy, and the worker's names this engine nowhere today. No delete: disconnecting a source
# leaves its key here, and the console says to revoke it in the source's own settings. Metadata
# read only, for the reason given above for providers.
path "connector_keys/data/+" {
  capabilities = ["create", "update"]
}

path "connector_keys/metadata/+" {
  capabilities = ["read"]
}

# Deny by omission is the default here, so the following are listed only to say they were
# considered and refused rather than forgotten:
#
#   sys/policy*          changing its own policy is the escalation this file exists to prevent
#   sys/unseal           the application is not the operator
#   auth/*               minting tokens for other roles
#   secret/data/*        static secrets, for the reason at the top
#   providers/metadata/* update or delete: see above
#   providers/delete/*   and destroy/*: removing a provider key is done at the server
