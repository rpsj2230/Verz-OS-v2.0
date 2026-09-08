"""What an install actually is, as code rather than as a promise M41 made on its behalf.

`brain.install` declares every value that belongs to the client. `docs/repository-map.md`
says an install touches nothing in this tree. Both are claims about a thing that did not
exist: **there was no installer, so nothing anywhere said what "an install" meant beyond a
release tag and an environment file**. This package is that sentence made checkable.

**The one rule the whole package serves: a client's values move through it and never into
it.** An installer is the single place a client's password, domain and company name are
handled, which makes it the single place they can leak. Three ways they leak and each is
refused here rather than remembered: a step that echoes what it set, a template generator
that emits a value it was handed, and a check that names the value it found instead of the
setting that held it. `brain.ops.independence.client_independence` cannot see any of the
three, because by the time a value reaches an installer's output it is in a log, a terminal
scrollback or a file that nothing sweeps.

**The second rule: a variables repository is not a fork.** M42.1 asks for per-client
variables in a separate private repository, and a reader in a hurry sees "a repository per
client" and reaches for the thing `duplication_gaps` exists to refuse. The difference is
what is inside: one environment file per install and nothing else. A repository holding an
environment file is configuration under version control; a repository holding a copy of the
product is a second copy of the product, and
`independence.A_SECOND_COPY_IS_SILENT_UNTIL_A_CLIENT_MEETS_THE_BUG_THAT_WAS_FIXED` is what
that costs. `variables.variables_repository_gaps` is the rule with teeth.

**Nothing here opens a socket, runs docker, or writes outside a caller's own path.** Every
module takes documents somebody else parsed, which is the split `brain.ops.compose` keeps and
for the same reason: a check that had to start containers could not be asked about a profile
nobody has deployed, and the profile nobody has deployed is the one this package is about.

Task ids: none
"""
