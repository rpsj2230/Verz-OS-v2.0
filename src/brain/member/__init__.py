"""The member application: the small surface a person who is not an administrator uses.

Three modules, split by the question each answers.

- `shell`: how somebody gets in and what they can open. Sign-in through the same identity
  provider the channels use, the session policy and the device list, and the member
  navigation, which is a second registry decided by the console's own `permitted`.
- `connections`: what this person is attached to. Personal account connections with
  per-source consent, the department-provided ones they inherit and may not detach, which
  channels they are reachable on, and quiet hours.
- `approvals`: the envelopes waiting on this person, what each one will do if answered, and
  what happens when nobody answers, which is nothing.

**Nothing is re-exported from here.** `brain.identity` re-exports four of its modules and
deliberately leaves `oidc` and `sessions` out, on the grounds that a caller should have to
name the module that turns an attacker-controlled string into a principal. Every module in
this package is in that position: `shell` decides what a member may open, `connections`
decides what may be detached, and `approvals` decides whether an answer counts. A package
import that hands those out by habit is one nobody reads twice.

**This package writes no SQLAlchemy model and no migration.** Where a leaf implies a table
(`personal_connection`, `channel_preference`), what is here is the type and the rules; the
tables belong to whoever owns `src/brain/tables`.
"""

from __future__ import annotations
