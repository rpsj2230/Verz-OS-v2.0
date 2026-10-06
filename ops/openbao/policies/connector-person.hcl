# What one read of a person's own refresh token may do with the secrets vault, for as long as its
# token lives.
#
# Task ids: M11.8.6
#
# No process holds this policy. A source consented to by each person for their own account keeps one
# refresh token per person, under connector_keys/oauth_refresh/<source>/<person>, and it is read only
# for that person's own question: the application mints a child token carrying this policy and
# nothing else, against the connector-person token role the release defines (TTL five minutes asked,
# no renewal, no default policy), reads the one slot and revokes it when the read ends. Only the
# application's policy may mint this role. The worker's may not, and the connector-run policy's lines
# stop one segment short of every person's slot, so no read made with nobody present can lease a
# person's token. Which person's slot a question reads is the code's to hold:
# brain.ops.connector_sync_run.PersonalKeys builds the one reference from the asker. See
# brain.ops.connector_lease.NOTHING_RUNNING_WITH_NOBODY_PRESENT_READS_A_PERSONS_CONSENT.
#
# Read on a person's slot and nothing else: no write, so a read cannot replace a consent (a rotated
# token is written back under connector-rotate.hcl); no metadata; and no line that reaches a source's
# key or a source's own refresh token, each of which is a segment shorter.
path "connector_keys/data/oauth_refresh/+/+" {
  capabilities = ["read"]
}

# Giving the token back at the end of the read. Granted here because the token carries no default
# policy, which is where revoke-self would otherwise come from.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
