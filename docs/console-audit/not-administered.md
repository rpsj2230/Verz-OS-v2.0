## Not administered here

| What | Why it is not a gap |
| --- | --- |
| `/*` | The page drawn for an address the console does not have, which manages nothing. |
| `/ask` | Asking a question is what the console is for a person, not something an administrator manages. |
| `/ask/documents/:documentId` | The document a citation on Ask opens, read at the asker's own reach; a person checking an answer, not an administrator managing anything. |
| `/auth/callback` | The end of a sign-in, drawn by the session module rather than by any screen. |
| `/signed-out` | The page a person lands on after signing out, which asks nothing and manages nothing. |
| `chat.conversation` | What a person asked and was answered belongs to them: kept by brain.chat.thread_store, listed, searched and reopened on Ask for that person alone, and never managed by anybody else. |
| `chat.message` | The same as chat.conversation: a person's own words, reported on and never managed. |
| `gate.channel_event` | The dedupe key of each inbound channel message, claimed once by brain.gate.event_store.first_delivery and read by nothing else; there is nothing in it for anybody to manage. |
| `GET /api/v1/knowledge/documents/{document_id}` | One document's passages for the page a citation opens, read at the caller's reach through the handler and policy the answer used; it writes nothing and manages nothing. |
| `GET /api/v1/threads` | A person's own conversations on Ask, for them alone and never anybody else's; nothing in it for an administrator to manage. |
| `GET /api/v1/threads/{thread_id}` | One of a person's own conversations reopened on Ask at the reach they hold now; nothing in it for an administrator to manage. |
| `GET /api/v1/threads/search` | A search of a person's own questions on Ask, for them alone; nothing in it for an administrator to manage. |
| `mem.mark` | The marks people put on their own answers, counted and read by nothing that decides an answer; no administrator manages a person's mark. |
| `POST /api/v1/answer` | The answer lane behind Ask, which writes no row an administrator manages. |
| `POST /api/v1/answer/mark` | A person marking an answer they were given helpful or not, one bit against its reference, which no administrator manages and nothing that answers reads. |
| `POST /api/v1/automation/tool-call` | Called by a running automation with its owner's reach, not by a person at a screen; installing the automation is the console's part. |
| `POST /api/v1/threads/{thread_id}/corrections` | A person marking the latest answer in their own conversation wrong, from Ask; a note in their thread the learning signal counts, and nothing in it for an administrator to manage. |
| `POST /api/v1/widget/sessions` | Where a website visitor's browser asks for a session, which holds nothing and writes no row an administrator manages; the sites it serves are the install's widget origins setting. |

**Every write to a route no area claims, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/answer` | `/ask` | Not applicable: Asking a question writes no row an administrator manages. | Not applicable: Asking a question is not a change to the system. | Not applicable: The answer is the behaviour, and tests/invariants hold it. |
| `POST /api/v1/answer/mark` | `/ask` | `test_a_person_marks_their_own_answer_and_no_other` in `tests/unit/test_learning_signal.py` (database, in CI) | Not applicable: A mark changes nothing the system does; the row is its own record, naming who marked which answer and when. | `test_a_person_marks_an_answer_they_were_given_with_one_action_and_no_words` in `tests/unit/test_answer_route_memory.py` |
| `POST /api/v1/threads/{thread_id}/corrections` | `/ask` | `test_every_thread_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_threads.py` (database, in CI) | Not applicable: Marking an answer in one's own conversation wrong changes no setting and nobody's access; the note is kept in the asker's own thread. | `test_every_thread_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_threads.py` (database, in CI) |
