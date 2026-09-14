/**
 * One agent's workspace, at the address `brain.console.workspace.deep_link` spells.
 *
 * **The address is the Python side's, and this page is a route for it rather than a second
 * scheme.** `DEEP_LINK_PREFIX` is `/agents/`, a tab is the segment after the agent, and
 * `resolve` gives one answer to a link naming a tab the reader cannot open and a link naming
 * a tab that does not exist. Here both open the first tab the strip holds, silently, which is
 * `openingTab`'s rule, so an address typed to probe for a tab lands where an address with no
 * tab at all does.
 *
 * **Nothing on this page decides what a person may see.** It asks, reads and hands over. A
 * failure is the API's sentence and the trace id, exactly as the overview renders one, and a
 * 404 is not explained: it is what an agent that does not exist and an agent this reader may
 * not see both look like, and `NO_ROUTE_ANSWERS_THE_WORKSPACE_ADDRESS_YET` records why it is
 * also what every agent looks like today.
 *
 * **The workspace is keyed on the agent and on the tab the address names.** A different agent
 * is a different workspace, so one agent's open tab and whatever was typed into it cannot turn
 * up on another's. A different tab in the address is a link somebody followed, from an alert
 * or a colleague, and landing on it is the point of M39.1.2.4's address. Selecting a tab by
 * hand does not change the address, so it rebuilds nothing, which is what M39.1.2.3 needs.
 *
 * **Two of the three regions have nothing to draw, and they draw nothing.** The dashboard
 * would be `brain.console.workspace.headline` and a tab's panel would be that tab's own read,
 * and no route serves either. The pane and the panel are still there, because moving between
 * them is the behaviour M39.1.2.3 and M39.1.2.5 describe, and an empty region says less than a
 * sentence claiming that this agent has no figures would.
 *
 * Loaded on demand, like the records screen, so that somebody who never opens an agent does
 * not download the workspace or its stylesheet. `tests/agent-page.test.tsx` holds that against
 * the static import graph from `main.tsx`.
 *
 * Task ids: M39.1.2.1, M39.1.2.3, M39.1.2.5, M39.1.1.5
 */

import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import { AgentWorkspace } from "../components/AgentWorkspace";
import { CompositionDiff } from "../components/CompositionDiff";
import { Notice } from "../ui/Notice";
import { agentWorkspaceApiPath, readAgentWorkspace } from "./agentQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

/** The page's own heading. The agent's name is the workspace's heading, beneath it. */
export const AGENT_HEADING = "Agent";

/**
 * One agent's answer. A separate component so that it can be keyed on the agent, which starts
 * a fresh request and a fresh workspace rather than showing one agent's state while the next
 * agent's answer is in flight.
 */
function AgentAnswer({
  agentId,
  tab,
}: {
  readonly agentId: string;
  readonly tab: string | undefined;
}) {
  const answer = useResource<unknown>(agentWorkspaceApiPath(agentId));
  const workspace = useMemo(() => readAgentWorkspace(answer.data), [answer.data]);

  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  if (workspace === null) {
    return null;
  }
  return (
    <AgentWorkspace
      key={tab ?? ""}
      agent={workspace.agent}
      tabs={workspace.tabs}
      {...(tab === undefined ? {} : { initialTab: tab })}
      renderTab={() => null}
      dashboard={null}
      profile={<CompositionDiff rows={workspace.composition} />}
    />
  );
}

export function Agent() {
  const { agentId, tab } = useParams();

  return (
    <article className="page">
      <h1>{AGENT_HEADING}</h1>
      {agentId === undefined ? null : <AgentAnswer key={agentId} agentId={agentId} tab={tab} />}
    </article>
  );
}
