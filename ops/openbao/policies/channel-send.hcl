# What one send from the worker may do with the secrets vault, for as long as its token lives.
#
# Task ids: M38.3.3.4
#
# No process holds this policy. The worker mints a child token carrying it and nothing else for each
# message its schedule sends (the evening digest first), against the channel-send token role the
# release defines (TTL five minutes asked, no renewal, no default policy), reads the channel's
# secret with that token and revokes it when the send ends. brain.ops.channel_lease argues the
# shape, and checks that the token the vault minted carries this policy alone before anything is
# read with it.
#
# Read on each channel wire's secret slot, named one at a time, and nothing else under that engine:
# the same engine holds the model providers' keys and the mail relay's password, and a send needs
# neither. A channel wire added to brain.channels is added here too, and
# tests/unit/test_vault_policies.py holds the two lists equal. No write, no delete and no metadata.
path "providers/data/channel_email" {
  capabilities = ["read"]
}

path "providers/data/channel_lark" {
  capabilities = ["read"]
}

path "providers/data/channel_slack" {
  capabilities = ["read"]
}

path "providers/data/channel_webhook" {
  capabilities = ["read"]
}

# Giving the token back at the end of the send. Granted here because the token carries no default
# policy, which is where revoke-self would otherwise come from.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
