Tools and workflows are parts of an agent in their own right (needs item 180, decided B on 2026-10-12). Leaf M39.1.1.1; no new leaf, the leaf already names the twelve.

- `workspace.Part` gains tools and workflows, both pinned references supplied by the install, so either can be attached as one and a persona still cannot. The architecture's count moves from ten to twelve with the enum (the test that reads it).
- Tools are held today (the agent's allowed tools and the presses that attach and detach them) and show in the agent page's reach block; nothing stores a workflow yet (M17.4.2), so a Workflows card says there are none rather than the part being left off the page until one exists.
- Install check `acceptance_checks_agent_parts` (order 1540), shown failing three ways: a part lost from the list, a persona accepted as an attachment, a page that does not show the tool.

Not claimed: that a stored workflow can be attached and followed, which is M17.4.2's. Memory in five kinds is the migration branch `M39/memory-kinds-migration` (0228), not this PR.

Reused: console/workspace.py Part, SUPPLY and workspace_gaps, agents/attachments.py, AgentProfile's reach block, the agent page check's route helpers.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
