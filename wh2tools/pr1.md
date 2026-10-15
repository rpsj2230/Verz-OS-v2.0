Team agents and personal agents (needs items 173 and 189, requirement ANY-060). Leaves M39.10.1, M39.10.2, M39.10.3, M39.10.6; M39.10.4 and M39.10.5 are not claimed (see below).

- The kind (team or personal) is read off the audience and stored nowhere. The agent roster, header and lifecycle view name it, and the builder's draft says which kinds its reader may make.
- A person with no authority over agents may start the builder and publish an agent only they can find, only while the new `personal_agents` switch is on (ships off). Only the install authority publishes a team agent; the refusal is in its own sentence. Administrators make both kinds with the switch off or on.
- A connector that reads one person's own mail, calendar and documents is bound only into a personal agent's ceiling, so a team agent naming it holds nothing from it. That holds the rule of item 189 whatever the owner chooses, and M39.10.5 (how a team agent may use mail) still waits for his answer.
- Console: the create flow offers the kind, and a person who may only make their own is shown the personal choice alone.
- Install check `acceptance_checks_agent_kinds` (check order 1500), shown failing with the product broken four ways. Mutation on the three guards: all caught.

Not claimed: M39.10.4 needs the owner's Google project (item 173) and a real mailbox, and M39.10.7 is a browser proof; the page test is in this PR.

Reused: agents/model.py Visibility.PERSONAL and visible_agent_ids, agents/creation.py new_audience, agent_builder_routes (`_reaches`, `_audience_asked`), the lifecycle routes, `brain.agents.binding.bound_capabilities`, the builder's check helpers.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
