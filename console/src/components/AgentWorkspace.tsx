/**
 * The frame inside one agent: a header, a strip of tabs, and a right pane with two views
 * (M39.1.2.3, M39.1.2.5).
 *
 * **The tab panel is rendered in one place, and that is the whole of "without losing tab
 * state".** The obvious layout puts the main area inside each branch of the pane
 * conditional, which keeps the reducer's state perfectly and throws away the DOM holding
 * everything the tab itself remembered: a filter somebody typed, a row they had open, where
 * they had scrolled to. The state survives and the screen does not. So the pane decides one
 * subtree and the main area is outside it, and
 * `tests/agent-workspace.test.tsx` asserts that by putting a component with its own state
 * inside the panel and taking it round a pane switch. See
 * `SWITCHING_THE_RIGHT_PANE_MOVES_NOTHING_BUT_THE_RIGHT_PANE`.
 *
 * **The panel is keyed on the tab, deliberately.** A different tab is a different thing, so
 * moving between tabs rebuilds the panel; moving between panes does not touch it. Without
 * the key, React would reconcile two different tabs' contents at the same position and one
 * tab would inherit the other's state, which is the same bug in the other direction.
 *
 * **Getting back to the roster is a link, and the key press moves focus to it rather than
 * following it.** See `THE_WAY_BACK_IS_A_LINK_AND_NEVER_A_NAVIGATION_THIS_COMPONENT_
 * PERFORMS`. The link is also the first thing in the workspace, so shift and tab reach it
 * from the strip with no handler at all, which is `tests/keyboard-access.test.tsx`'s
 * argument about the skip link one level down.
 *
 * **The arrow keys exist because the tabs pattern takes them away from the tab key.** A
 * strip of tabs is one stop in the document's tab order, with the arrows moving inside it,
 * which is what a roving `tabIndex` of `0` and `-1` implements. That is the one place in
 * this console where a keyboard handler is not a sign that somebody used the wrong element.
 * `scripts/check-boundaries.mjs` refuses a positive `tabIndex`, and `-1` is not one: it
 * takes an element out of the tab order rather than reordering it.
 *
 * **Arrowing selects as it moves, and that is a trade-off with a trigger for changing it.**
 * WAI-ARIA calls this automatic activation and prefers it while showing a panel is cheap.
 * It is cheap here because nothing in this file fetches: `renderTab` is handed a tab key and
 * whatever it returns is the caller's. The day a tab's panel issues its own request, holding
 * the right arrow down is seven requests, and the answer then is manual activation, where
 * the arrows move focus and Enter opens. Written here because the change is easy to make and
 * the reason to make it is easy to miss.
 *
 * **Nothing here decides what a person may see.** The strip is what
 * `brain.console.workspace.tab_strip` returned, already narrowed, and a tab the caller holds
 * no grant for and a tab with nothing in it were one absence before this component was
 * handed the list. There is no filter here and nothing to filter with, and there is nowhere
 * in this markup for a number of tabs.
 *
 * Task ids: M39.1.2.3, M39.1.2.5
 */

import { useCallback, useReducer, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AgentHeader } from "./AgentHeader";
import {
  FIRST_PANE,
  PANES,
  ROSTER_ADDRESS,
  headingId,
  openingTab,
  panelId,
  reduce,
  tabByStep,
  tabId,
  type AgentIdentity,
  type Pane,
  type WorkspaceTabView,
} from "./agentWorkspaceState";
import "../styles/agent-workspace.css";

/** The way out, and the first thing in the workspace. */
export const BACK_TO_ROSTER = "Back to all agents";

/** What the strip is called to somebody who cannot see it. */
export const TAB_STRIP_LABEL = "Workspace tabs";

/** What the right-hand column is called, and what its two buttons switch. */
export const RIGHT_PANE_LABEL = "Right pane";
export const PANE_SWITCH_LABEL = "Show in the right pane";

/**
 * What each pane is called.
 *
 * A table of labels, which `src/ui/Status.tsx` refuses for a state word and which is right
 * here for the opposite reason: a state word belongs to the API and this vocabulary belongs
 * to the console. `PANES` is declared in `agentWorkspaceState.ts` and nothing on the Python
 * side names either member, so there is no original for these to drift from. Frozen, so a
 * module cannot give one viewer a different label from another.
 */
export const PANE_LABELS: Readonly<Record<Pane, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
});

interface AgentWorkspaceProps {
  readonly agent: AgentIdentity;
  /** The strip, as the API answered it for this reader. Rendered in the order given. */
  readonly tabs: readonly WorkspaceTabView[];
  /** Where a deep link asked to land. Absent means the first tab in the strip. */
  readonly initialTab?: string;
  /** One tab's contents. Called with the selected tab's key and nothing else. */
  readonly renderTab: (tab: string) => ReactNode;
  /** The agent's figures. `brain.console.workspace.headline` is what fills this. */
  readonly dashboard: ReactNode;
  /** What the agent is: its composition beside the template it came from. */
  readonly profile: ReactNode;
}

export function AgentWorkspace({
  agent,
  tabs,
  initialTab,
  renderTab,
  dashboard,
  profile,
}: AgentWorkspaceProps) {
  const [state, dispatch] = useReducer(reduce, {
    tab: openingTab(tabs, initialTab),
    pane: FIRST_PANE,
  });

  const roster = useRef<HTMLAnchorElement>(null);
  // One element per tab, so a key press can move focus without asking the document what is
  // on the screen. A query selector here would find another workspace's strip in a test
  // that rendered two of them, and would be quietly right until it was not.
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  const onStripKey = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.preventDefault();
        roster.current?.focus();
        return;
      }
      let next: string | undefined;
      if (event.key === "ArrowRight") {
        next = tabByStep(tabs, state.tab, 1);
      } else if (event.key === "ArrowLeft") {
        next = tabByStep(tabs, state.tab, -1);
      } else if (event.key === "Home") {
        next = tabs[0]?.tab;
      } else if (event.key === "End") {
        next = tabs[tabs.length - 1]?.tab;
      }
      if (next === undefined) {
        return;
      }
      event.preventDefault();
      dispatch({ kind: "select-tab", tab: next });
      // Focus moves now rather than in an effect. Every tab button is already in the
      // document, so this is independent of the state update, and an effect would move
      // focus on every render that happened to change the selection, including one caused
      // by a click, which would drag focus about under somebody's mouse.
      buttons.current.get(next)?.focus();
    },
    [tabs, state.tab],
  );

  const current = tabs.find((one) => one.tab === state.tab);

  return (
    <section className="agent-workspace" aria-labelledby={headingId(agent.agentId)}>
      <Link className="agent-workspace__roster" to={ROSTER_ADDRESS} ref={roster}>
        {BACK_TO_ROSTER}
      </Link>

      <AgentHeader agent={agent} />

      <div className="agent-workspace__body">
        <div className="agent-workspace__main">
          <div
            className="agent-tabs"
            role="tablist"
            aria-label={TAB_STRIP_LABEL}
            onKeyDown={onStripKey}
          >
            {tabs.map((one) => (
              <button
                key={one.tab}
                type="button"
                role="tab"
                id={tabId(agent.agentId, one.tab)}
                aria-controls={panelId(agent.agentId, one.tab)}
                aria-selected={one.tab === state.tab}
                tabIndex={one.tab === state.tab ? 0 : -1}
                className={
                  one.tab === state.tab ? "agent-tabs__tab agent-tabs__tab--current" : "agent-tabs__tab"
                }
                ref={(element) => {
                  if (element) {
                    buttons.current.set(one.tab, element);
                  } else {
                    buttons.current.delete(one.tab);
                  }
                }}
                onClick={() => {
                  dispatch({ kind: "select-tab", tab: one.tab });
                }}
              >
                {one.label}
              </button>
            ))}
          </div>

          {current === undefined ? null : (
            <div
              key={current.tab}
              className="agent-tabs__panel"
              role="tabpanel"
              id={panelId(agent.agentId, current.tab)}
              aria-labelledby={tabId(agent.agentId, current.tab)}
            >
              <p className="agent-tabs__purpose">{current.purpose}</p>
              {renderTab(current.tab)}
            </div>
          )}
        </div>

        <aside className="agent-workspace__aside" aria-label={RIGHT_PANE_LABEL}>
          <div className="agent-panes" role="group" aria-label={PANE_SWITCH_LABEL}>
            {PANES.map((pane) => (
              <button
                key={pane}
                type="button"
                className={
                  pane === state.pane ? "agent-panes__button agent-panes__button--current" : "agent-panes__button"
                }
                aria-pressed={pane === state.pane}
                onClick={() => {
                  dispatch({ kind: "show-pane", pane });
                }}
              >
                {PANE_LABELS[pane]}
              </button>
            ))}
          </div>

          {/*
           * One expression, and the tab panel is nowhere inside it. Moving the main area in
           * here is the change this component is arranged to make impossible; see the note
           * at the top of the file.
           */}
          {state.pane === "dashboard" ? dashboard : profile}
        </aside>
      </div>
    </section>
  );
}
