On an agent's page its steward and administrators are told that other people's conversations with it happened (needs item 121, decided B on 2026-10-13). Leaf M39.11.1 (new), register row DEC-121B; its proof M39.11.2 is on the migration branch.

- Who, when and whether the agent answered, declined or failed, from the run record (`ops.agent_run`: counts and names from closed lists), never from a thread. The view has no field that could carry a question, an answer, a title or a count.
- Readers: the steward and a holder of the lifecycle authority over the agent's row. A personal agent tells nobody but its owner anything.
- The select policy that lets those rows be read is the migration branch (0227, `M39/agent-run-overseen-migration`, no PR). Without it the list is empty, so this merges safely first.

Reused: agent_conversation_routes, console/agent_conversations, StoredAgentRuns, steward_names, holds(AGENT_LIFECYCLE_CAPABILITY).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
