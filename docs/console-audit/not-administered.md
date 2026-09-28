## Not administered here

| What | Why it is not a gap |
| --- | --- |
| `/*` | The page drawn for an address the console does not have, which manages nothing. |
| `/ask` | Asking a question is what the console is for a person, not something an administrator manages. |
| `/auth/callback` | The end of a sign-in, drawn by the session module rather than by any screen. |
| `/signed-out` | The page a person lands on after signing out, which asks nothing and manages nothing. |
| `chat.conversation` | What a person asked and was answered belongs to them; no store queries it yet (brain.chat.threads) and usage is reported without the words. |
| `chat.message` | The same as chat.conversation: a person's own words, reported on and never managed. |
| `gate.channel_event` | The dedupe key of each inbound channel message, claimed once by brain.gate.event_store.first_delivery and read by nothing else; there is nothing in it for anybody to manage. |
| `POST /api/v1/answer` | The answer lane behind Ask, which writes no row an administrator manages. |
| `POST /api/v1/automation/tool-call` | Called by a running automation with its owner's reach, not by a person at a screen; installing the automation is the console's part. |

**Every write to a route no area claims, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/answer` | `/ask` | Not applicable: Asking a question writes no row an administrator manages. | Not applicable: Asking a question is not a change to the system. | Not applicable: The answer is the behaviour, and tests/invariants hold it. |
