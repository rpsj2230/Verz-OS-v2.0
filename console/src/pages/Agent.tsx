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
 * not see both look like, and `brain.agent_routes` answers the two with one status and one
 * body.
 *
 * **The workspace is keyed on the agent and on the tab the address names.** A different agent
 * is a different workspace, so one agent's open tab and whatever was typed into it cannot turn
 * up on another's. A different tab in the address is a link somebody followed, from an alert
 * or a colleague, and landing on it is the point of M39.1.2.4's address. Selecting a tab by
 * hand does not change the address, so it rebuilds nothing, which is what M39.1.2.3 needs.
 *
 * **The dashboard is the agent's figures and the profile is what it is assembled from.** The
 * dashboard is `brain.console.workspace.headline` at the basis this reader holds, which the
 * route now serves; the profile is the composition diff beside the connectors, skills and
 * channels that same answer carries. Each block draws nothing when the answer carries nothing
 * for it, because a heading over an empty pane is a count of hidden things in words.
 *
 * **One tab's panel draws something, and the rest draw nothing.** The Automations tab draws the
 * automation gallery (M39.6.1.3), which `brain.automation_gallery_routes` serves behind that tab's
 * own read; every other panel would be its tab's own read and no route serves one, which is why
 * only Automations and Settings are ever in the strip. The gallery is asked for here rather than
 * inside the panel, because `components/AgentWorkspace.tsx` rebuilds a panel on every tab change
 * and says the day a panel fetches is the day holding an arrow key becomes a stream of requests.
 * It is asked the first time the panel is shown and not before, so a person who never opens the
 * tab costs nothing, and never again for moving between tabs. After an install the same address
 * is asked again under a new version, so nothing on the page is rebuilt.
 *
 * Loaded on demand, like the records screen, so that somebody who never opens an agent does
 * not download the workspace or its stylesheet. `tests/agent-page.test.tsx` holds that against
 * the static import graph from `main.tsx`.
 *
 * The profile begins with the agent's model: its tier, and a provider and model an administrator
 * may pin for it (`components/AgentModelPin.tsx`, M5.7.3).
 *
 * Task ids: M39.1.2.1, M39.1.2.3, M39.1.2.5, M39.1.1.5, M39.6.1.3, M5.7.3
 */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import { AgentCapabilities, AgentFiguresView } from "../components/AgentAssembly";
import { AgentWorkspace } from "../components/AgentWorkspace";
import { AgentModelPin } from "../components/AgentModelPin";
import { AgentAutomations } from "../components/AgentAutomations";
import { AutomationGallery } from "../components/AutomationGallery";
import { CompositionDiff } from "../components/CompositionDiff";
import { agentWorkspaceApiPath, readAgentWorkspace } from "./agentQuery";
import { readModelChoice } from "./agentModelPinQuery";
import { agentAutomationsApiPath } from "./agentAutomationsQuery";
import { AUTOMATIONS_TAB, automationGalleryApiPath } from "./automationGalleryQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's own heading. The agent's name is the workspace's heading, beneath it. */
export const AGENT_HEADING = "Agent";

/**
 * The automation gallery for one agent, asked for the first time its panel is shown and again
 * after each install.
 *
 * A render prop rather than a component the panel mounts, so the request belongs to the page and
 * not to the panel; see the note at the top of the file.
 */
function WithAutomationGallery({
  agentId,
  children,
}: {
  readonly agentId: string;
  readonly children: (panel: ReactNode) => ReactNode;
}) {
  const [shown, setShown] = useState(false);
  const [installs, setInstalls] = useState(0);
  const gallery = useResource<unknown>(shown ? automationGalleryApiPath(agentId) : null, installs);
  // The installed automations are asked for with the gallery and again after an install, a start
  // or a stop, so the list and the cards never disagree about what this reader has installed.
  const automations = useResource<unknown>(
    shown ? agentAutomationsApiPath(agentId) : null,
    installs,
  );
  const onShown = useCallback(() => {
    setShown(true);
  }, []);
  const onInstalled = useCallback(() => {
    setInstalls((count) => count + 1);
  }, []);
  return (
    <>
      {children(
        <>
          {shown ? (
            <AgentAutomations
              agentId={agentId}
              automations={automations}
              onChanged={onInstalled}
            />
          ) : null}
          <AutomationGallery
            agentId={agentId}
            gallery={gallery}
            onShown={onShown}
            onInstalled={onInstalled}
          />
        </>,
      )}
    </>
  );
}

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
  // The tier and the pinned model, for a reader the workspace gave a profile (M5.7.3).
  const choice = useMemo(() => readModelChoice(answer.data), [answer.data]);

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
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
  const drawn = (automations: ReactNode) => (
    <AgentWorkspace
      key={tab ?? ""}
      agent={workspace.agent}
      tabs={workspace.tabs}
      {...(tab === undefined ? {} : { initialTab: tab })}
      renderTab={(key) => (key === AUTOMATIONS_TAB ? automations : null)}
      dashboard={
        <AgentFiguresView
          divergent={workspace.divergent}
          {...(workspace.figures === undefined ? {} : { figures: workspace.figures })}
        />
      }
      profile={
        <>
          {choice === null ? null : <AgentModelPin agentId={agentId} choice={choice} />}
          <CompositionDiff rows={workspace.composition} />
          <AgentCapabilities
            connectors={workspace.connectors}
            skills={workspace.skills}
            channels={workspace.channels}
          />
        </>
      }
    />
  );
  return workspace.tabs.some((one) => one.tab === AUTOMATIONS_TAB) ? (
    <WithAutomationGallery agentId={agentId}>{drawn}</WithAutomationGallery>
  ) : (
    drawn(null)
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
