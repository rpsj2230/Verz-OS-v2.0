A person can now mark a chat answer helpful or unhelpful by replying with one word and the answer's reference. They are told the same sentence whatever happened to the mark. This is M16.6.4, channel half; it has no migration.

- **The line.** A person's own chat answer (a direct reply, or the private aside in a group) ends with "Reply helpful <trace> or unhelpful <trace> to mark this answer." The reference is the request trace the answer ran under, in the console route's own alphabet and length limit.
- **The reader.** `brain.channels.marks.read_mark` accepts a first line that is one of the two words and a reference, after any mention the surface adds, and nothing else. A reason after the reference makes it not a mark, and the message is answered as an ordinary one.
- **The writer.** `inbound.reply_for` writes through the console's own `StoredMarks`, so who may mark is the console's rule: the request ledger must say the answer was given to the person marking, inside `MARKABLE_FOR`.
- **One sentence for every outcome.** Counted, refused because the answer was somebody else's, or naming nothing: all get the correction seam's `CORRECTION_ACKNOWLEDGEMENT`. A mark typed in a group is acknowledged in the sender's own conversation.
- **No mark line on room postings.** A room's posting never carries the line, even when everybody in the room holds the same and the room reads the asker's own answer.

**Not built.** Card buttons wait on the owner item the coordinator is filing: whether a card press may write. The text line already works on every surface.

**Mutations: 10 run, 9 caught, 1 survived.** The survivor was a redundant second copy of the room rule; I removed it, and the one place that strips the line is documented. Full table in the commit message.

**Tests.**
- On a fresh database, invariants plus every chat, channel, inbound, Lark, card, halt, connector, correction, mark and escalation test file: 2824 passed, 1 failed. The failure was the effects classification for the new `AnswerMarks.mark`; I fixed it.
- After merging main: 1621 passed, 0 failed (invariants plus the marks, chat, inbound, correction, learning-signal, answer-route-memory and effects files).
- mypy (`--platform linux`), ruff, format and the traceability sweep are clean.

No leaf is claimed: built and tested, not yet seen on an install.

Reused: the console's `StoredMarks`, `marks_of` and `MARKABLE_FOR`; the correction seam's acknowledgement and mention grammar; `chat_answer`'s reply and room planning; `inbound.reply_for`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
