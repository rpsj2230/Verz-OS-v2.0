# What one write of a rotated refresh token may do with the secrets vault, for as long as its token
# lives.
#
# Task ids: M11.8.6
#
# No process holds this policy. A vendor that rotates refresh tokens (Xero issues a new one with
# every renewal and voids the old) hands the read that renewed access a new token, and that read
# keeps it: the worker or the application mints a child token carrying this policy and nothing else,
# against the connector-rotate token role the release defines (TTL five minutes asked, no renewal,
# no default policy), patches the source's refresh token slot with it and revokes it when the write
# ends. brain.ops.connector_lease argues the shape, and checks that the token the vault minted
# carries this policy alone before anything is written with it.
#
# Patch on a refresh token's slot and nothing else. Patch, because kv version 2 merges a patch into
# a slot that already holds a version without the caller reading it, so this token cannot read the
# token it replaces; no read, no create, no update, no delete and no metadata. The directory is one
# segment deeper than every key (connector_keys/oauth_refresh/<source>), so nothing a source's key
# or a write grant's key is kept at is reachable from here. See
# brain.ops.connector_lease.A_ROTATED_GRANT_IS_WRITTEN_BACK_BY_A_ROLE_THAT_CANNOT_READ_IT.
path "connector_keys/data/oauth_refresh/+" {
  capabilities = ["patch"]
}

# And a person's own refresh token (M11.8.6), one segment deeper, rotated by the read made for that
# person's question: the same patch and nothing more, so this token cannot read the person's token it
# replaces either. Which person's slot is patched is the code's to hold, as it is for the read
# (brain.ops.connector_sync_run.PersonalKeys).
path "connector_keys/data/oauth_refresh/+/+" {
  capabilities = ["patch"]
}

# Giving the token back at the end of the write. Granted here because the token carries no default
# policy, which is where revoke-self would otherwise come from.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
