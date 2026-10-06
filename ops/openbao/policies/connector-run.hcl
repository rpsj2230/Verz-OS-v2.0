# What one connector run may do with the secrets vault, for as long as its token lives.
#
# Task ids: M31.3.2.2, M31.3.2.3, M31.3.2.4, M11.8.6
#
# No process holds this policy. The worker mints a child token carrying it and nothing else for each
# attempt to read a connected source, against the connector-run token role the installer creates
# (TTL fifteen minutes, no renewal, no default policy), reads the source's key with that token and
# revokes it when the attempt ends. brain.ops.connector_lease argues the shape, and checks that the
# token the vault minted carries this policy alone before anything is read with it.
#
# Read on a source's key and nothing else under that engine: no write, no delete and no metadata,
# because a run reads a source and has no screen to tell. One path segment for every source, for the
# reason worker.hcl used to give when the worker read these itself; the narrowing to the run's own
# source is brain.ops.connector_sync_run.WorkerConnectorKeys, before the vault is asked.
path "connector_keys/data/+" {
  capabilities = ["read"]
}

# The refresh token a person's consent to a source bought (M11.8.6), read by the run that renews
# that source's access, and nothing more: no write, so a run cannot replace it. A rotated token is
# written back under connector-rotate.hcl, by a token of its own. One segment deeper than every key,
# so it is named here on its own line rather than reached by the line above.
path "connector_keys/data/oauth_refresh/+" {
  capabilities = ["read"]
}

# Giving the token back at the end of the run. Granted here because the token carries no default
# policy, which is where revoke-self would otherwise come from.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}

# Deliberately absent: auth/token/renew-self, so a run stuck on a slow source loses its authority at
# the TTL rather than extending it; auth/token/create, so a run token cannot mint another; and
# lookup-self, which a run has no use for.
