# What a release's deploy step may do with the secrets vault, and nothing it may not.
#
# Task ids: M31.3.2.2, M31.3.2.1
#
# Until 2026-09-29 a release that changed a file in this directory was not in force until three
# people with unseal pieces generated a root token and loaded it. On 2026-09-29 two changes waited
# on that and nobody could find three pieces, and the owner decided (needs-rupash 114) that every
# release applies its own policies, engines and roles during deploy, with a token kept root-only on
# the server. This is that token's policy. `ops/openbao/apply-release.sh` is what uses it.
#
# WHAT IT IS, SAID PLAINLY: a token that may rewrite the other policies may widen what the
# application's and the worker's tokens reach, so it is as sensitive as the vault itself and lives
# where the seal key lives, in a root-only file. What it is not: it reads no secret, writes no
# secret value, mints no token and removes nothing, and it cannot rewrite its own policy or the
# default one, so it cannot widen itself. Every use is in the audit log under its own accessor,
# where a root token's use would be indistinguishable from any administrator's.
#
# Minted with -no-default-policy, so the two token paths it needs are granted here by name.

# Every other policy: write it, and read it back to prove it took.
path "sys/policies/acl/*" {
  capabilities = ["create", "update", "read", "list"]
}

path "sys/policies/acl" {
  capabilities = ["list"]
}

# Its own policy and the default one are read-only to it. In OpenBao the most specific path rule
# wins, so these two replace the rule above for their exact paths rather than adding to it: a
# token that could rewrite its own policy, or the default one every other token carries, could
# grant itself anything. A release that needs this file changed says so, and the change is made
# with a root token generated from the recovery key (ops/openbao/UNSEAL.md, In an emergency).
path "sys/policies/acl/deploy" {
  capabilities = ["read"]
}

path "sys/policies/acl/default" {
  capabilities = ["read"]
}

# Engines: list them, and enable one a release adds. No delete, so no engine and nothing in one can
# be removed by a deploy; enabling a path already in use is refused by the vault itself.
path "sys/mounts" {
  capabilities = ["read"]
}

path "sys/mounts/*" {
  capabilities = ["create", "update", "read"]
}

# Token roles, today the one a connector run's token is minted against. Defining a role mints
# nothing: minting against it takes auth/token/create/<role>, which this policy does not grant.
path "auth/token/roles/*" {
  capabilities = ["create", "update", "read"]
}

# The connected sources' slots: their metadata, which says what scopes a key must have and holds no
# key. The data path beside it is deliberately absent, so no deploy can read or write a vendor's key.
path "connector_keys/metadata/*" {
  capabilities = ["create", "update", "read"]
}

# Its own standing and renewal. A periodic token nothing renews lapses, and every deploy renews it.
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
