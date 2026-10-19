# What the console no longer shows

The owner asked on 2026-09-28 that the console stop carrying what an administrator does not need:
internal identifiers in page text, developer wording, panels drawn twice and controls that explain how
the thing is built. This is the record of each removal and why, so the next cleanup has something to
extend and nobody puts one back to tidy a screen.

It is held by `console/tests/console-cleanup.test.tsx`, which mounts every page the console registers
and refuses a UUID, a snake_case identifier, a table's name, an address of the API, a word that says how
the console is built and a heading drawn twice, in the text outside the Advanced section. The page
cases it uses are the ones `screen-states` and `phone-width` use. A removal is added here in the same
change that makes it, and an excuse in that test is argued in the second table below, which the test
reads.

## What was removed

| What was removed | From | Why |
| --- | --- | --- |
| The "You" card's nine rows (principal id, entitlement digest, employment, assurance, channel, withheld verbs, second factor, department, name) | `/` the Overview | Identifiers belong in Advanced, and the sign-in banner already says what a person can act on. |
| The install card's commit hash and its "decides readiness" and "reported only" chips | `/` the Overview | They described the readiness probe, not the install, and nobody could act on them. |
| The lede "according to the API" | `/` the Overview | It said how the page is built instead of what it shows. |
| The register id as the first column, the requirement picker that listed every id, the form drawn open under the table, the served paragraph above the form and the crumb written as text | `/requirement-checks` | The id is under each requirement and in the drawer, and the rest repeated what the row and the drawer already said. |
| The document's own identifier printed under its title | `/ask/documents/:documentId` | The title says which document it is, and the identifier is in the address for anybody who needs it. |
| "exactly as the API answered them" under the Records heading | `/records` | It said how the page is built, not what the rows are, and an administrator does not know what the API is. |
| The principal's identifier after "Stopped by" and in the resume confirmation | `/stop` | An identifier is not a person, and who stopped the work is on the audit log. |
| The principal's identifier after "Added by" on a rule's card | `/rules` | The same: the card now says when it was added, and the audit log says by whom. |
| A vendor's field name drawn as a form label, such as `reply_url` and `signing_secret` | `/channels/:name` | A variable name is not a label, so the field now reads as words, such as "Reply address", while its name stays what is sent. |
| A card heading that repeats the page's own title directly under it | `/artifacts`, `/jobs`, `/packs`, `/subscribers`, `/corrections`, `/company/estate`, `/company/activity` | Two headings saying the same thing read as two panels, so the card keeps its label for a screen reader and draws it no more. |
| A second heading called "Channels" for where a person is told, beside the one for the chat accounts they are connected on | `/me` | Two different things under one name read as a panel drawn twice, so the second is now "Where you are told". |

Names for the two identifiers removed from `/stop` and `/rules` need the API to send them, as
`brain.people_names` does for the audit log and the approvals. That is a change to two routes, not a
console edit, and it is not done here; until it is, the page says when and the audit log says who.

## What is excused, and why

The sweep allows a rule on a page only where that page exists to show exactly that thing. Each entry
is checked in both directions, so one that stops matching anything on its page is refused.

| Page | Rule | Why an administrator needs to see it |
| --- | --- | --- |
| `/tools`, `/tools/:name`, `/approvals`, `/approvals/:suspensionId`, `/agents/drafts/:draftId` | identifiers | A tool is named by what it is called in the agent's manifest and on the approval card, and an administrator reads and writes that name. |
| `/classification`, `/classification/:entity`, `/classification/:entity/:column`, `/records/:entity` | identifiers | These pages are the plain view of a table's own columns, whose names are what a grant, a policy row and a support conversation use. |
| `/rules`, `/service-accounts/:clientId` | identifiers | A name an administrator types when writing a rule, shown as the form it takes, or an account's own name. |
| `/channels/:name/:view` | an address of the API | The address copied into the chat vendor's settings is the thing the page is for. |
| `/connectors`, `/connectors/new-api` | developer words | This is where an administrator hands the product another company's API, so the words are the subject of the page. |
| `/features` | developer words | These inputs take a pasted document, and the format is the instruction. |

"Coming soon" is not excused anywhere except as the lead of the kit's own note and of a disabled
action's reason (`kit/parts.tsx` `NOTE_LEADS`), which are the owner's words for a screen that is not
built yet. Anywhere else it is refused.

A question for the owner, not decided here: whether "Coming soon" should be worded "Not available yet"
everywhere, since the first promises a date nobody has set. The kit already has `not-yet` for the
version that does not.
