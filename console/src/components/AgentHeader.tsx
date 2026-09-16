/**
 * The top of an agent's workspace: who this agent is, who answers for it, and where it came
 * from (M39.1.2.1).
 *
 * **Six things are asked for and three of them are questions with separate answers.** An
 * agent that reached this console is one the reader's audience covers, so its name is a
 * fact they already hold and the avatar is drawn from that name. The role line, the owner
 * and the template lineage are not: each is a value the API answers separately, and it
 * answers by sending the key or not sending it.
 *
 * **The header is the record, so a lock does not belong on it.** `src/ui/Lock.tsx` draws a
 * withheld field and argues in its own words why the field's existence may be disclosed at
 * all: the lock is for a field inside a record whose existence was already legitimately
 * disclosed, and the record-level rule is a different rule. This is the record level. A
 * lock in the row where the owner goes would say this agent has a steward the reader may
 * not be told about, which is a fact they did not have, and a dash or the word unknown says
 * it just as clearly. So an absent field contributes no element: no label, no row, no
 * placeholder. See `AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE`.
 *
 * **Nothing here is composed out of a longer value.** The role line arrives as a sentence
 * or does not arrive. A first line cut out of the persona would be a summary written in a
 * browser, out of prompt material `brain.agents.model` says is never parsed, and two
 * consoles would cut it in two places.
 *
 * **Nothing here counts anything**, which is the same rule `src/ui/Chip.tsx` states about
 * itself: no number of tabs, no number of connectors, no number of anything the reader is
 * not also being shown.
 *
 * Task ids: M39.1.2.1
 */

import type { AgentIdentity } from "./agentWorkspaceState";
import { headingId, initials } from "./agentWorkspaceState";
import "../styles/agent-workspace.css";

/** The label over the current steward. `AgentAudience.owner_id`, never `created_by`. */
export const OWNER_LABEL = "Owner";

/** The label over the template an agent was installed from, and the version it is pinned to. */
export const LINEAGE_LABEL = "Template";

/**
 * The label over who built the agent, which is a different person from the steward.
 *
 * "Built by" rather than "Created by", because the row beside it says Owner and the pair has
 * to read as two questions rather than as two words for one: who answers for this now, and
 * who made it. The field arrives only for a reader of the Settings tab, and a reader without
 * it gets no row at all, which is `AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE`.
 */
export const BUILDER_LABEL = "Built by";

/**
 * The word before a version number.
 *
 * A word rather than a `v`, because the number beside it is
 * `brain.agents.template.TemplateInstance.template_version`, an integer somebody publishes,
 * and `v4` reads as a release tag of the product rather than as the pin this agent is on.
 */
export const VERSION_WORD = "version";

export function AgentHeader({ agent }: { readonly agent: AgentIdentity }) {
  // Computed, not counted. The value is a boolean and never reaches the DOM: a header that
  // rendered an empty definition list would be an element where facts go, and one that
  // rendered how many facts survived would be the subtraction disclosure with a number on
  // it. There is no third branch.
  const hasFacts =
    agent.ownerId !== undefined || agent.createdBy !== undefined || agent.lineage !== undefined;

  return (
    <header className="agent-header">
      {/*
       * Decorative, and hidden, because it is the name again in two letters. Announcing it
       * would read the name twice to somebody who cannot see either of them.
       */}
      <span className="agent-header__avatar" aria-hidden="true">
        {initials(agent.displayName)}
      </span>

      <div className="agent-header__identity">
        <h2 className="agent-header__name" id={headingId(agent.agentId)}>
          {agent.displayName}
        </h2>

        {agent.roleLine === undefined ? null : (
          <p className="agent-header__role">{agent.roleLine}</p>
        )}

        {hasFacts ? (
          <dl className="agent-header__facts">
            {agent.ownerId === undefined ? null : (
              <div className="fields__row">
                <dt>{OWNER_LABEL}</dt>
                <dd>
                  <code>{agent.ownerId}</code>
                </dd>
              </div>
            )}

            {agent.createdBy === undefined ? null : (
              <div className="fields__row">
                <dt>{BUILDER_LABEL}</dt>
                <dd>
                  <code>{agent.createdBy}</code>
                </dd>
              </div>
            )}

            {agent.lineage === undefined ? null : (
              <div className="fields__row">
                <dt>{LINEAGE_LABEL}</dt>
                <dd>
                  <code>{agent.lineage.templateId}</code>{" "}
                  <span className="agent-header__version">
                    {VERSION_WORD} {agent.lineage.version}
                  </span>
                </dd>
              </div>
            )}
          </dl>
        ) : null}
      </div>
    </header>
  );
}
