An install check for the wave-three milestone (M38.2.2.4): an agent installed from a template, answering with knowledge and memory.

The parts each have a check of their own; this one asks whether they compose. In one rolled-back transaction: the catalogue's knowledge agent (`internal_helpdesk`) is installed from the gallery over a copy signed with a key made for the check and enabled; a member of acceptance_a states a memory and asks a question their department's document answers, naming the agent. The install's request row says that agent answered, the model (a stand-in that keeps its prompt and asks for the document search once) was shown the document through the agent's tool and the memory as a hint beside the question, and the answer cites the document and carries none of the memory. A colleague is answered from the document and sent none of the memory; a member of the other department naming the agent is outside its audience and is answered by nobody's agent.

- The model is a stand-in, so the task is added to `docs/proof-sweep-holds.json` with M38.2.2.3's reason (a real question to a real model is the owner's).
- Mutation, three rows, all caught (table in the commit message); five broken-product tests, one per seam.
- No migration, no route or screen change.

Verified locally: ruff, ruff format, mypy --platform linux, traceability, compatibility, tests/invariants, test_acceptance.py, test_proof_sweep.py and the two new modules' tests on PostgreSQL at head.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
