/**
 * My workspace: what a person has asked, what they can call, what has been learnt about them, what
 * they keep, and what they can ask about. For a reader who administers nothing.
 *
 * `docs/screens.html` SCREEN 12 is the design of record, and this is its layout in its order: four
 * figures across the top (questions this month, agents I can call, my budget, learned about me),
 * then My agents beside What it learned about me, then Knowledge I own beside Connected accounts,
 * then What I can ask about. Each card's title is the design's, one column on a phone.
 *
 * **Every figure is the person's own, and the page asks nothing that could be about somebody
 * else.** `brain.mine_routes` takes no parameter naming a person. It opens on the member grant,
 * which `brain.member.shell` refuses to share with any administrative screen, so a person holding
 * nothing administrative reaches this page and a person holding only administrative grants does
 * not. A 404 is the API saying this caller may not open it, and the page does not explain further.
 *
 * **What the design draws and nothing records is a sentence where the design draws it.** The
 * corrections under the questions figure, the Undo all control, the Verified and Used 30d columns
 * of the knowledge card, and the connected accounts are each the API's own sentence, because
 * nothing on an install records them. `brain.console.own_things` names the decisions each would
 * need.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M27.7.28
 */

import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { when } from "./artifactsQuery";
import {
  PROVISION_WORDS,
  WORKSPACE_API_PATH,
  monthly,
  ownAgents,
  readBudget,
  spentOf,
  wasRead,
  whereItRuns,
  type Workspace,
} from "./myWorkspaceQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const WORKSPACE_HEADING = "My workspace";
export const WORKSPACE_CRUMB = "Use › My workspace";
export const WORKSPACE_LEDE =
  "What you asked, the agents you can call, what has been learnt about you, and what you keep. " +
  "Everything on this page is yours or already visible to you, and it shows nothing your access " +
  "would not already return in an answer.";

export const READING_WORKSPACE = "Reading your workspace.";

/** Under a refusal: which grant opens the page, which is the same sentence for everybody. */
export const OPENS_ON_THE_MEMBER_GRANT =
  "This page opens for anybody holding the member grant, and for nobody else, whatever else they " +
  "hold. If you expected to see it, ask your department administrator for it.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

export const NO_AGENTS = "There are no agents you can call.";
export const NO_CEILING = "No budget of your own is set.";
export const NOTHING_LEARNED = "Nothing learnt about you is shown.";
export const NO_ITEMS = "You do not look after any knowledge items.";
export const MORE_ITEMS = "You look after more items than this page reads at once.";

export const AGENTS_CAPTION = "Agents I can call";
export const ITEMS_CAPTION = "Knowledge I own";
export const LEARNED_CAPTION = "What it learned about me";

function Figures({ workspace }: { readonly workspace: Workspace }) {
  const budget = readBudget(workspace);
  const month = wasRead(budget) ? monthly(budget.panel) : null;
  return (
    <section className="card">
      <h2>At a glance</h2>
      <dl className="fields" aria-label="My workspace at a glance">
        <div className="fields__row">
          <dt>Questions this month</dt>
          <dd>
            <span>{String(workspace.asked.questions)}</span>
            <p className="note">{workspace.asked.corrections}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Agents I can call</dt>
          <dd>
            <span>{String(workspace.agents.length)}</span>
            <p className="note">{`${String(ownAgents(workspace.agents))} of them your own`}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>My budget</dt>
          <dd>
            {!wasRead(budget) ? (
              <p className="note">{budget.unread}</p>
            ) : month === null ? (
              <p className="note">{NO_CEILING}</p>
            ) : (
              <span>{spentOf(month)}</span>
            )}
          </dd>
        </div>
        <div className="fields__row">
          <dt>Learned about me</dt>
          <dd>
            <span>{String(workspace.learned.length)}</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function MyAgents({ workspace }: { readonly workspace: Workspace }) {
  return (
    <section className="card">
      <h2>My agents</h2>
      {workspace.agents.length === 0 ? (
        <p className="note">{NO_AGENTS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={AGENTS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Agent</th>
                <th scope="col">Source</th>
                <th scope="col">Where it runs</th>
                <th scope="col">Used 30d</th>
              </tr>
            </thead>
            <tbody>
              {workspace.agents.map((one) => (
                <tr key={one.agent_id}>
                  <td>
                    <code>{one.agent_id}</code>
                  </td>
                  <td>{PROVISION_WORDS[one.provision] ?? one.provision}</td>
                  <td>{whereItRuns(one)}</td>
                  <td>{String(one.uses)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WhatItLearned({ workspace }: { readonly workspace: Workspace }) {
  return (
    <section className="card">
      <h2>{LEARNED_CAPTION}</h2>
      {workspace.learned.length === 0 ? (
        <p className="note">{NOTHING_LEARNED}</p>
      ) : (
        <ul aria-label={LEARNED_CAPTION}>
          {workspace.learned.map((one) => (
            <li key={one.memory_id}>
              <strong>{one.statement}</strong>
              <p className="note">
                {`${one.stated ? "You said this" : "Inferred"}, ${when(one.formed_at)}`}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="note">{workspace.learned_undo}</p>
    </section>
  );
}

function KnowledgeIOwn({ workspace }: { readonly workspace: Workspace }) {
  return (
    <section className="card">
      <h2>{ITEMS_CAPTION}</h2>
      {workspace.knowledge.length === 0 ? (
        <p className="note">{NO_ITEMS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={ITEMS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Visible to</th>
              </tr>
            </thead>
            <tbody>
              {workspace.knowledge.map((one) => (
                <tr key={one.item_id}>
                  <td>
                    <code>{one.item_id}</code>
                  </td>
                  <td>
                    <code>{one.department ?? one.level}</code>
                    {one.department === null ? null : <span className="note"> {one.level}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {workspace.knowledge_truncated ? <p className="note">{MORE_ITEMS}</p> : null}
      <p className="note">{workspace.knowledge_not_shown}</p>
    </section>
  );
}

export function MyWorkspace() {
  const answer = useResource<Workspace>(WORKSPACE_API_PATH);

  return (
    <article className="page">
      <p className="note">{WORKSPACE_CRUMB}</p>
      <h1>{WORKSPACE_HEADING}</h1>
      <p className="lede">{WORKSPACE_LEDE}</p>

      {answer.failure ? (
        <section className="card">
          <Notice
            title={
              answer.failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK
            }
            traceId={answer.failure.traceId}
          >
            <p>{answer.failure.message}</p>
            {answer.failure.status === 404 ? (
              <p className="note">{OPENS_ON_THE_MEMBER_GRANT}</p>
            ) : null}
          </Notice>
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          {READING_WORKSPACE}
        </p>
      ) : null}

      {answer.data === null ? null : (
        <>
          <p>{`Signed in as ${answer.data.display_name}.`}</p>
          <Figures workspace={answer.data} />
          <MyAgents workspace={answer.data} />
          <WhatItLearned workspace={answer.data} />
          <KnowledgeIOwn workspace={answer.data} />
          <section className="card">
            <h2>Connected accounts</h2>
            <p>{answer.data.accounts}</p>
          </section>
          <section className="card">
            <h2>What I can ask about</h2>
            <p>{answer.data.can_ask_about}</p>
          </section>
        </>
      )}
    </article>
  );
}
