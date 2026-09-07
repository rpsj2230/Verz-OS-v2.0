"""Payload shapes the staff-source adapters are parsed against, and the traps in each.

`tests/fixtures/cassettes.py` is the same idea for connectors and this is deliberately a
second file rather than an addition to it. A cassette is a recorded HTTP exchange for a
business source: a status, headers, a rate limit and the failure modes a connector must
survive. None of the five sources here is one of those, none of them has an entry in
`brain.ops.limits.SOURCE_CEILINGS`, and `tests/invariants/test_cassettes.py` parametrises
its contract test over `brain.connectors` alone. Adding a directory to `Source` would put a
roster endpoint into a corpus whose invariants are about rate ceilings and would have said
nothing about either.

**These shapes are reconstructed from vendor documentation, not recorded from a live
tenant.** Nobody here holds an Admin SDK credential, an Entra application registration, a
Lark contact scope or a directory bind, and the whole point of building adapters before
go-live is that they do not wait on one. Each entry below says which endpoint it stands for
so the day somebody does hold a credential the recording can replace the reconstruction
field by field. Where a trap is recorded rather than reasoned it is marked, and the one
recorded payload this file does reuse is Lark's: `cassettes.LARK-200-code-permission` shows
a permission failure arriving inside an HTTP 200 with a non-zero `code`, and the contact
endpoint answers in the same envelope as the Base endpoint that cassette was taken from.

**Every trap here is a shape that parses without erroring and produces a wrong roster.** A
payload that fails to parse is a payload somebody fixes. The failures worth recording are
the ones that succeed: a Sheets row that is shorter than its header because the trailing
cells were empty, an LDAP attribute that is a list of one, an AD referral that is an entry
with no distinguished name, and a Lark refusal that reads as a company with no staff. Each
of those produces a roster that is confidently wrong, and on a source trusted with
completeness a confidently short roster is a mass revocation.

Task ids: M1.6.4, M1.6.5, M1.6.6, M1.6.8
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------- a hand-kept spreadsheet
#: What `csv.reader` yields from a staff export somebody maintains by hand: a header row and
#: rows of strings, with no types and no promises.
#:
#: Four traps, all of which parse:
#:
#: - **A ragged row.** The third row has four cells against the header's five, because the
#:   person who typed it left the last column empty and their editor did not pad it. Zipping
#:   header to row without padding shifts nothing here and raises nothing; it simply drops
#:   the last field, which on a wider sheet is the difference between a department and none.
#: - **A blank trailing row.** Every spreadsheet exported by a human has one. It has an empty
#:   address, and `StaffRecord` refuses that, so a parser that does not skip it raises on the
#:   whole file for a row containing nothing.
#: - **Headers with case and spacing of their own.** `Work Email` and ` Department ` are what
#:   people type. An exact-match column lookup finds neither.
#: - **A department column on a source that may not assert one.** It is here precisely so the
#:   test can show which layer refuses it.
SPREADSHEET_EXPORT: tuple[tuple[str, ...], ...] = (
    ("Work Email", "Full Name", " Department ", "Groups", "Left?"),
    ("ada@example.com", "Ada Lovelace", "engineering", "approvers", ""),
    ("grace@example.com", "Grace Hopper", "engineering", "", ""),
    ("katherine@example.com", "Katherine Johnson", "finance"),
    ("alan@example.com", "Alan Turing", "engineering", "", "yes"),
    ("", "", "", "", ""),
)

#: The same export with one person listed twice, in two capitalisations.
#:
#: A directory that exports one address twice is a directory; a spreadsheet two people edit
#: is worse. `Roster` refuses this at construction and the adapter must not soften it into a
#: silent de-duplication, because which of the two rows survives decides what the person is
#: in and neither row is more true than the other.
SPREADSHEET_WITH_A_REPEATED_PERSON: tuple[tuple[str, ...], ...] = (
    ("Work Email", "Full Name"),
    ("ada@example.com", "Ada Lovelace"),
    ("ADA@example.com", "A. Lovelace"),
)

# ------------------------------------------------------------------------- Google Sheets
#: `GET /v4/spreadsheets/{id}/values/{range}`, the `spreadsheets.values.get` response.
#:
#: Two traps beyond the spreadsheet ones, and both are documented behaviour of this endpoint
#: rather than anything a person did wrong:
#:
#: - **Trailing empty cells are omitted from a row, and trailing empty rows from `values`.**
#:   So a row is not the width of the header and the sheet is not the height of the range.
#: - **`range` comes back as the range that was read, which is a bound rather than a
#:   measurement.** A request for `A1:E4` that returns four rows may be four rows or may be
#:   the first four of four hundred. Nothing in the body distinguishes them, which is why
#:   completeness has to be read off the range and not off the row count.
GOOGLE_SHEET_VALUES: dict[str, Any] = {
    "range": "Staff!A1:E1000",
    "majorDimension": "ROWS",
    "values": [
        ["Work Email", "Full Name", "Department", "Groups", "Left?"],
        ["ada@example.com", "Ada Lovelace", "engineering", "approvers", ""],
        ["grace@example.com", "Grace Hopper", "engineering"],
        ["katherine@example.com", "Katherine Johnson", "finance", "auditors"],
    ],
}

#: The same read against a range the sheet filled exactly.
#:
#: Four data rows in a range four data rows tall. The sheet may be four rows long or may be
#: four thousand, and this body cannot tell you which, so the honest answer is that the read
#: is not known to be the whole list.
GOOGLE_SHEET_VALUES_AT_THE_RANGE_LIMIT: dict[str, Any] = {
    "range": "Staff!A1:E5",
    "majorDimension": "ROWS",
    "values": [
        ["Work Email", "Full Name", "Department", "Groups", "Left?"],
        ["ada@example.com", "Ada Lovelace", "engineering", "approvers", ""],
        ["grace@example.com", "Grace Hopper", "engineering", "", ""],
        ["katherine@example.com", "Katherine Johnson", "finance", "auditors", ""],
        ["alan@example.com", "Alan Turing", "engineering", "", ""],
    ],
}

# ------------------------------------------------------- Google Workspace Admin Directory
#: `GET /admin/directory/v1/users?customer=my_customer`, page one of two.
#:
#: `nextPageToken` is the trap and it is the important one in this file. A caller that reads
#: one page gets a syntactically perfect roster containing half the company, and a roster
#: trusted with completeness that contains half the company removes the other half.
#:
#: `suspended` and `archived` are two fields and both mean the person is not working here.
#: `archived` is the one that is missed, because it is newer and because an archived user
#: still appears in `users.list` looking exactly like everybody else.
#:
#: `aliases` matters for the rename question rather than for the roster: when Workspace
#: renames somebody it keeps the old address as an alias, so the alias list is where the
#: evidence of a rename survives after the primary address has moved.
GOOGLE_WORKSPACE_USERS_PAGE_ONE: dict[str, Any] = {
    "kind": "admin#directory#users",
    "etag": '"etag-page-one"',
    "users": [
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000001",
            "primaryEmail": "ada@example.com",
            "name": {"givenName": "Ada", "familyName": "Lovelace", "fullName": "Ada Lovelace"},
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Engineering",
            "aliases": ["a.lovelace@example.com"],
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000002",
            "primaryEmail": "grace@example.com",
            "name": {"givenName": "Grace", "familyName": "Hopper", "fullName": "Grace Hopper"},
            "suspended": False,
            "archived": True,
            "orgUnitPath": "/Engineering",
        },
    ],
    "nextPageToken": "Q29udGludWVGcm9tSGVyZQ",
}

#: The last page: no `nextPageToken`, which is the only thing that says the walk finished.
#:
#: The meeting room is here on purpose. A Workspace customer's user list contains resources,
#: shared mailboxes and service accounts, and this one has no `primaryEmail` at all. A parser
#: that refuses a row without an address refuses the whole company for a room.
GOOGLE_WORKSPACE_USERS_PAGE_TWO: dict[str, Any] = {
    "kind": "admin#directory#users",
    "etag": '"etag-page-two"',
    "users": [
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000003",
            "primaryEmail": "katherine@example.com",
            "name": {
                "givenName": "Katherine",
                "familyName": "Johnson",
                "fullName": "Katherine Johnson",
            },
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Finance",
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000004",
            "name": {"fullName": "Meeting Room 3"},
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Resources",
        },
    ],
}

#: `GET /admin/directory/v1/groups/{group}/members`, flattened to the shape a caller holds
#: after walking it: the group's own address, and the addresses of its members.
#:
#: Group membership is a second endpoint in this API and not a field on the user, which is
#: why the adapter takes it as a second argument. Folding it into the user parse would make
#: the adapter unusable by an installation that has not granted the group scope.
GOOGLE_WORKSPACE_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "approvers@example.com": ("ada@example.com",),
    "auditors@example.com": ("katherine@example.com",),
}

# --------------------------------------------------------------------- Microsoft Entra ID
#: `GET /v1.0/users?$select=id,displayName,userPrincipalName,mail,accountEnabled,department`.
#:
#: **`mail` and `userPrincipalName` are different fields and the difference is the join.**
#: The UPN is what somebody signs in with and Keycloak brokers to; `mail` is what the outside
#: world writes to, is frequently a different domain after an acquisition, and is null for a
#: user with no mailbox. An adapter that joins on `mail` binds the roster to an address the
#: sign-in identity does not carry, and the symptom is a person who exists in the staff list
#: and matches no principal.
#:
#: `@odata.nextLink` is the continuation, and unlike Google's it is a whole URL.
#:
#: `proxyAddresses` carries the old address in lower-case `smtp:` after a rename, with the
#: current one in upper-case `SMTP:`. That is the same rename evidence as Workspace's alias
#: list, spelled differently, and the case of the prefix is the whole of it: Ada's upper-case
#: entry is her live mail address on the acquired company's domain, which is not a former
#: address and is what a case-insensitive read would report as one.
ENTRA_USERS_PAGE_ONE: dict[str, Any] = {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users",
    "value": [
        {
            "id": "8f1a0e5c-0000-4000-8000-000000000001",
            "displayName": "Ada Lovelace",
            "userPrincipalName": "ada@example.com",
            "mail": "ada.lovelace@example.co.uk",
            "accountEnabled": True,
            "department": "Engineering",
            "proxyAddresses": [
                "SMTP:ada.lovelace@example.co.uk",
                "smtp:ada.l@example.com",
            ],
        },
        {
            "id": "8f1a0e5c-0000-4000-8000-000000000002",
            "displayName": "Grace Hopper",
            "userPrincipalName": "grace@example.com",
            "mail": None,
            "accountEnabled": False,
            "department": "Engineering",
        },
    ],
    "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skiptoken=X1234",
}

#: The last page. No `@odata.nextLink`, and one guest account.
#:
#: A guest's UPN is mangled: `katherine_partner.example.com#EXT#@example.onmicrosoft.com`.
#: They are somebody else's employee with a foothold in this tenant, they are in `/users`
#: like everybody else, and a roster that lists them as staff gives a supplier's employee a
#: principal in this system.
ENTRA_USERS_PAGE_TWO: dict[str, Any] = {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users",
    "value": [
        {
            "id": "8f1a0e5c-0000-4000-8000-000000000003",
            "displayName": "Katherine Johnson",
            "userPrincipalName": "katherine@example.com",
            "mail": "katherine@example.com",
            "accountEnabled": True,
            "department": "Finance",
        },
        {
            "id": "8f1a0e5c-0000-4000-8000-000000000009",
            "displayName": "Kit Partner",
            "userPrincipalName": "kit_supplier.example#EXT#@example.onmicrosoft.com",
            "mail": "kit@supplier.example",
            "accountEnabled": True,
            "department": None,
        },
    ],
}

#: Group membership as a caller holds it after walking `/groups/{id}/members`, keyed on the
#: group's `displayName` because that is what a person writing a group rule types.
ENTRA_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "Approvers": ("ada@example.com",),
    "Auditors": ("katherine@example.com",),
}

# ------------------------------------------------------------------------------ Lark
#: `GET /open-apis/contact/v3/users/find_by_department`, page one.
#:
#: **A non-zero `code` inside an HTTP 200 is how this vendor refuses**, which is recorded
#: rather than reasoned: `cassettes.LARK-200-code-permission` is a real Base call answering
#: `{"code": 91403}` inside a 200, and contact endpoints use the same envelope. A parser that
#: checks the status and reads `data.items` records a refusal as a company with no staff.
#:
#: `email` is the person's own address and `enterprise_email` is the work one. Both are
#: present, `email` is the one that is populated more often, and it is the wrong one.
#:
#: `status` has three flags that all mean not working here and they are not the same thing:
#: `is_frozen` is suspended, `is_resigned` is left, `is_activated` false is never signed in.
#:
#: `department_ids` are opaque `od-` identifiers. Passing one through as a department name
#: creates a department called `od-...` that no scope predicate will ever match, and the
#: person then sees nothing with nothing anywhere saying why.
LARK_USERS_PAGE_ONE: dict[str, Any] = {
    "code": 0,
    "msg": "success",
    "data": {
        "has_more": True,
        "page_token": "AQD9SL9dAQ",
        "items": [
            {
                "open_id": "ou_0000000000000000000000000000001",
                "union_id": "on_0000000000000000000000000000001",
                "user_id": "ada.lovelace",
                "name": "Ada Lovelace",
                "email": "ada.personal@gmail.example",
                "enterprise_email": "ada@example.com",
                "department_ids": ["od-engineering"],
                "status": {
                    "is_frozen": False,
                    "is_resigned": False,
                    "is_activated": True,
                    "is_exited": False,
                },
            },
            {
                "open_id": "ou_0000000000000000000000000000002",
                "union_id": "on_0000000000000000000000000000002",
                "user_id": "grace.hopper",
                "name": "Grace Hopper",
                "email": "grace.personal@gmail.example",
                "enterprise_email": "grace@example.com",
                "department_ids": ["od-engineering"],
                "status": {
                    "is_frozen": False,
                    "is_resigned": True,
                    "is_activated": True,
                    "is_exited": False,
                },
            },
        ],
    },
}

#: The last page: `has_more` false is the only thing that says the walk finished.
LARK_USERS_PAGE_TWO: dict[str, Any] = {
    "code": 0,
    "msg": "success",
    "data": {
        "has_more": False,
        "page_token": "",
        "items": [
            {
                "open_id": "ou_0000000000000000000000000000003",
                "union_id": "on_0000000000000000000000000000003",
                "user_id": "katherine.johnson",
                "name": "Katherine Johnson",
                "email": "",
                "enterprise_email": "katherine@example.com",
                "department_ids": ["od-finance"],
                "status": {
                    "is_frozen": False,
                    "is_resigned": False,
                    "is_activated": True,
                    "is_exited": False,
                },
            }
        ],
    },
}

#: A refusal, arriving as an HTTP 200 with a business code in the body.
#:
#: 99991663 is an app-permission failure: the tenant has not granted `contact:user.base:read`
#: to this application. It is the ordinary state of a Lark app on the day it is installed and
#: before anybody approves the scope, so it is the response an installation is most likely to
#: meet first.
LARK_USERS_REFUSED: dict[str, Any] = {
    "code": 99991663,
    "msg": "app permission denied",
    "data": {},
}

#: Department identifier to the name a person would recognise, as a caller holds it after
#: `GET /open-apis/contact/v3/departments`. A second call, like Workspace's groups.
LARK_DEPARTMENT_NAMES: dict[str, str] = {
    "od-engineering": "engineering",
    "od-finance": "finance",
}

#: User-group membership as a caller holds it after walking `contact/v3/group/member/simplelist`,
#: keyed on the group's name and valued by work addresses.
LARK_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "approvers": ("ada@example.com",),
    "auditors": ("katherine@example.com",),
}

#: A page in which somebody is in two known departments at once.
#:
#: Lark's `department_ids` is a list and a person genuinely can be in several. There is one
#: `department` on a roster record and a department is the scope a person's grants are bounded
#: by, so choosing one of two is choosing how far somebody can see.
LARK_USERS_IN_TWO_DEPARTMENTS: dict[str, Any] = {
    "code": 0,
    "msg": "success",
    "data": {
        "has_more": False,
        "page_token": "",
        "items": [
            {
                "open_id": "ou_0000000000000000000000000000005",
                "union_id": "on_0000000000000000000000000000005",
                "user_id": "jean.bartik",
                "name": "Jean Bartik",
                "enterprise_email": "jean@example.com",
                "department_ids": ["od-engineering", "od-finance"],
                "status": {"is_frozen": False, "is_resigned": False, "is_activated": True},
            }
        ],
    },
}

# ---------------------------------------------------------------------- the same tenant later
#: Workspace a month later, after Ada married and her primary address changed.
#:
#: The two things that make this a rename rather than a departure and an arrival are both in
#: the payload and neither is her name: the `id` is the one from
#: `GOOGLE_WORKSPACE_USERS_PAGE_ONE`, and the old address is now in `aliases`, which is what
#: Workspace does on a rename and is why mail keeps arriving.
#: One page and no continuation, so it is the whole company as it stands that month.
GOOGLE_WORKSPACE_AFTER_A_RENAME: dict[str, Any] = {
    "kind": "admin#directory#users",
    "users": [
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000001",
            "primaryEmail": "ada.byron@example.com",
            "name": {"givenName": "Ada", "familyName": "Byron", "fullName": "Ada Byron"},
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Engineering",
            "aliases": ["ada@example.com", "a.lovelace@example.com"],
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000002",
            "primaryEmail": "grace@example.com",
            "name": {"givenName": "Grace", "familyName": "Hopper", "fullName": "Grace Hopper"},
            "suspended": False,
            "archived": True,
            "orgUnitPath": "/Engineering",
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000003",
            "primaryEmail": "katherine@example.com",
            "name": {
                "givenName": "Katherine",
                "familyName": "Johnson",
                "fullName": "Katherine Johnson",
            },
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Finance",
        },
    ],
}

#: Workspace a month later, where a new joiner has been given a departed colleague's address.
#:
#: The identifier is new and the address is not. Reissuing an address is ordinary practice and
#: the point of it is that mail keeps working, which is exactly what makes it dangerous here:
#: the address is the join to a sign-in identity, so completing it would hand the new joiner
#: whatever the previous holder held.
GOOGLE_WORKSPACE_AFTER_A_REISSUE: dict[str, Any] = {
    "kind": "admin#directory#users",
    "users": [
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000001",
            "primaryEmail": "ada@example.com",
            "name": {"givenName": "Ada", "familyName": "Lovelace", "fullName": "Ada Lovelace"},
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Engineering",
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000077",
            "primaryEmail": "grace@example.com",
            "name": {"givenName": "Gina", "familyName": "Harper", "fullName": "Gina Harper"},
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Engineering",
        },
        {
            "kind": "admin#directory#user",
            "id": "100000000000000000003",
            "primaryEmail": "katherine@example.com",
            "name": {
                "givenName": "Katherine",
                "familyName": "Johnson",
                "fullName": "Katherine Johnson",
            },
            "suspended": False,
            "archived": False,
            "orgUnitPath": "/Finance",
        },
    ],
}

# --------------------------------------------------------------- LDAP and Active Directory
#: The result of a paged `SearchRequest` against Active Directory, as every LDAP client
#: hands it over: a list of `(distinguished name, attributes)` pairs.
#:
#: **Every attribute value is a list, whatever the schema says.** LDAP has no single-valued
#: read: `mail` comes back as `["ada@example.com"]`, and a parser that uses it directly
#: produces the work address `['ada@example.com']`, which `StaffRecord` accepts because it
#: contains an `@`.
#:
#: **Attribute names are case-insensitive in the protocol and case-sensitive in a dict.** A
#: server that answers `sAMAccountName` to a request for `samaccountname` is behaving
#: correctly, and the lookup that misses returns nothing rather than raising.
#:
#: **A referral is an entry with no distinguished name.** Active Directory answers a search
#: that crosses a partition boundary with a continuation reference in the result stream, and
#: a client that iterates results without checking gets an entry that is not a person. It is
#: also evidence: a referral means the search did not cover everything it was asked about.
#:
#: **`userAccountControl` is a bit field and 0x2 is ACCOUNTDISABLE.** There is no boolean.
#: 512 is a normal enabled account, 514 is that account disabled, 66048 is enabled with a
#: password that does not expire. Comparing the whole number to 512 marks half the estate
#: disabled; testing the bit is the only reading that works.
#:
#: **The distinguished name is not stable and `objectGUID` is.** Moving somebody between
#: organisational units rewrites their DN, which is why the DN is not the identity here.
ACTIVE_DIRECTORY_ENTRIES: tuple[tuple[str | None, dict[str, list[str]]], ...] = (
    (
        "CN=Ada Lovelace,OU=Engineering,DC=example,DC=com",
        {
            "objectGUID": ["{0a1b2c3d-0000-4000-8000-000000000001}"],
            "sAMAccountName": ["ada"],
            "userPrincipalName": ["ada@example.com"],
            "mail": ["ada@example.com"],
            "displayName": ["Ada Lovelace"],
            "department": ["engineering"],
            "userAccountControl": ["512"],
            "memberOf": [
                "CN=Approvers,OU=Groups,DC=example,DC=com",
                "CN=All Staff,OU=Groups,DC=example,DC=com",
            ],
        },
    ),
    (
        "CN=Grace Hopper,OU=Engineering,DC=example,DC=com",
        {
            "objectGUID": ["{0a1b2c3d-0000-4000-8000-000000000002}"],
            "sAMAccountName": ["grace"],
            "userPrincipalName": ["grace@example.com"],
            "mail": ["grace@example.com"],
            "displayName": ["Grace Hopper"],
            "department": ["engineering"],
            "userAccountControl": ["514"],
            "memberOf": [],
        },
    ),
    (
        "CN=Katherine Johnson,OU=Finance,DC=example,DC=com",
        {
            "objectGUID": ["{0a1b2c3d-0000-4000-8000-000000000003}"],
            "sAMAccountName": ["katherine"],
            "userPrincipalName": ["katherine@example.com"],
            "mail": ["katherine@example.com"],
            "displayName": ["Katherine Johnson"],
            "department": ["finance"],
            "userAccountControl": ["66048"],
            "memberOf": ["CN=Auditors,OU=Groups,DC=example,DC=com"],
        },
    ),
    (
        "CN=svc-backup,OU=Service Accounts,DC=example,DC=com",
        {
            "objectGUID": ["{0a1b2c3d-0000-4000-8000-00000000000f}"],
            "sAMAccountName": ["svc-backup"],
            "displayName": ["Backup Service"],
            "userAccountControl": ["512"],
        },
    ),
)

#: The same search when Active Directory hands back a continuation reference, which it does
#: whenever the subtree crosses into another domain in the forest.
AD_ENTRIES_WITH_A_REFERRAL: tuple[tuple[str | None, dict[str, list[str]]], ...] = (
    *ACTIVE_DIRECTORY_ENTRIES[:1],
    (None, {"ref": ["ldap://child.example.com/DC=child,DC=example,DC=com"]}),
)

#: A plain OpenLDAP server, which has none of Active Directory's account fields.
#:
#: There is no `userAccountControl`, so nothing in the payload can say a person has left; the
#: identity is `entryUUID` rather than `objectGUID`; and the department is `ou` rather than
#: `department`. An install behind plain LDAP therefore has a roster that can add and can
#: never say anybody has gone, which is a real limitation and not a parsing failure.
OPENLDAP_ENTRIES: tuple[tuple[str | None, dict[str, list[str]]], ...] = (
    (
        "uid=ada,ou=People,dc=example,dc=com",
        {
            "entryUUID": ["0a1b2c3d-0000-4000-8000-000000000001"],
            "uid": ["ada"],
            "mail": ["ada@example.com"],
            "cn": ["Ada Lovelace"],
            "ou": ["engineering"],
        },
    ),
    (
        "uid=grace,ou=People,dc=example,dc=com",
        {
            "entryUUID": ["0a1b2c3d-0000-4000-8000-000000000002"],
            "uid": ["grace"],
            "mail": ["grace@example.com"],
            "cn": ["Grace Hopper"],
            "ou": ["engineering"],
        },
    ),
)

#: What an LDAP server answers when its own administrative limit truncated the search.
#:
#: Result code 4 is `sizeLimitExceeded`. Active Directory's default `MaxPageSize` is a
#: thousand, and a company of twelve hundred whose client does not page gets a thousand
#: people and a result code nobody read. Every one of the remaining two hundred is then
#: absent from a roster that promised completeness.
LDAP_SIZE_LIMIT_EXCEEDED: int = 4

#: The ordinary success code, for the pair the tests need.
LDAP_SUCCESS: int = 0
