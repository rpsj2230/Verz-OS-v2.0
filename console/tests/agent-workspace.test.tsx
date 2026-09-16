/**
 * Inside one agent: the header, the right pane, the keyboard, and the composition diff.
 *
 * Four leaves, and each of them is a way this surface could look right and be wrong.
 *
 * **The header must not show that something was withheld.** An agent that reached this
 * console is one the reader's audience covers, so its name is already theirs. The role line,
 * the owner and the lineage are separate answers, and a withheld one arrives exactly as an
 * absent one does: as a key that is not there. What is held here is the rendering half of
 * that rule. An absent field contributes no label, no row, no placeholder and no lock, so an
 * agent whose owner was withheld and an agent the API sent without one are the same markup.
 * The reading half, where a payload becomes these shapes, is held beside the page that reads
 * one.
 *
 * **Switching the right pane must not lose the tab.** The reducer keeping the tab is half of
 * it, and it is asserted over sequences of actions rather than over one switch. The other half
 * is the DOM: a layout that rendered the tab panel once inside each pane's branch would keep
 * the state perfectly and throw away whatever the tab itself was holding, so a component with
 * state of its own is taken round a switch and checked on the way back.
 *
 * **The keys must actually move focus, and there must be a way back.** Every keyboard test
 * reads `document.activeElement` after the key, never whether a handler exists.
 *
 * **A diff row carries both sides or it is not a row.** A path marked as differing with its
 * value withheld tells a reader three facts that silence does not. And divergence is read off
 * the source the row carries and never off its two columns, because `brain.agents.upgrade`
 * names the case where both answers coincide and the path is still a decision somebody made
 * on this agent.
 *
 * **Nothing here decides what a person may see.** The strip arrives narrowed by
 * `brain.console.workspace.tab_strip`, and the tests assert it is drawn exactly as handed over.
 * Every vocabulary these components copy from the Python side is read back out of it through
 * `support/agentWorkspace.ts`, so no assertion here compares a console constant with itself.
 *
 * Task ids: M39.1.2.1, M39.1.2.3, M39.1.2.5, M39.1.1.5
 */

import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { fireEvent, render } from "@testing-library/react";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { AgentHeader, LINEAGE_LABEL, OWNER_LABEL, VERSION_WORD } from "../src/components/AgentHeader";
import {
  AgentWorkspace,
  BACK_TO_ROSTER,
  PANE_LABELS,
  TAB_STRIP_LABEL,
} from "../src/components/AgentWorkspace";
import {
  CompositionDiff,
  DIFF_CAPTION,
  INSTANCE_COLUMN,
  PATH_COLUMN,
  SOURCE_COLUMN,
  TEMPLATE_COLUMN,
  groupByPart,
} from "../src/components/CompositionDiff";
import { DataTable, type GridColumn } from "../src/components/DataTable";
import {
  AGENT_ADDRESS_PREFIX,
  FIRST_PANE,
  PANES,
  ROSTER_ADDRESS,
  SET_ON_THIS_AGENT,
  initials,
  reduce,
  type AgentIdentity,
  type DiffRow,
  type Pane,
  type WorkspaceAction,
  type WorkspaceState,
  type WorkspaceTabView,
} from "../src/components/agentWorkspaceState";
import {
  asPythonName,
  backendDeepLinkPrefix,
  backendFieldSource,
  backendHiddenCountNames,
  backendPartOfPath,
  backendTabCount,
  backendTabOrder,
  membersOf,
  optionalMembersOf,
} from "./support/agentWorkspace";
import { backendEnumMembers, backendLockText } from "./support/python";
import { parseConsoleSource, propNamesOf } from "./support/typescript";

const WORKSPACE_MODULE = "src/brain/console/workspace.py";
const STATE_MODULE = "src/components/agentWorkspaceState.ts";

// ------------------------------------------------------------------------------- fixtures

/**
 * The strip a reader holding every tab would be handed, in `brain.console.workspace.TABS`
 * order and spelled with that module's `Tab` values.
 *
 * Read rather than written out, for the reason `support/agentWorkspace.ts` gives: a strip in
 * an order this file invented is a strip nobody will ever see. The labels and purposes are
 * the fixture's, and none of them carries a digit, so a digit on the screen came from a
 * component rather than from the data.
 */
function backendStrip(): WorkspaceTabView[] {
  const values = backendEnumMembers(WORKSPACE_MODULE, "Tab");
  return backendTabOrder().map((member) => {
    const tab = values[member];
    if (tab === undefined) {
      throw new Error(`TABS names Tab.${member}, which the Tab enum does not declare.`);
    }
    return {
      tab,
      label: `${tab.slice(0, 1).toLocaleUpperCase("en-GB")}${tab.slice(1)}`,
      purpose: `What the ${tab} tab is for.`,
    };
  });
}

const STRIP: readonly WorkspaceTabView[] = backendStrip();

/** One agent, with every fact the header can show. The only digit is the pinned version. */
const AGENT: AgentIdentity = {
  agentId: "quote-helper",
  displayName: "Quote Helper",
  roleLine: "Drafts a first answer to a pricing question.",
  ownerId: "steward-one",
  lineage: { templateId: "pricing-desk", version: 4 },
};

/** The same agent with one fact taken away, as the API sends a fact it will not tell. */
function without<K extends keyof AgentIdentity>(key: K): AgentIdentity {
  const copy: Record<string, unknown> = { ...AGENT };
  delete copy[key];
  return copy as unknown as AgentIdentity;
}

/**
 * The composition part a manifest path supplies, in the spelling `brain.console.workspace`
 * serialises: the value of the `Part` member `PART_OF_PATH` maps the path to.
 */
function partOf(path: string): string {
  const member = backendPartOfPath()[path];
  const value = member === undefined ? undefined : backendEnumMembers(WORKSPACE_MODULE, "Part")[member];
  if (value === undefined) {
    throw new Error(`PART_OF_PATH does not map ${path} to a Part value; the fixture is stale.`);
  }
  return value;
}

const FROM_TEMPLATE = backendFieldSource("TEMPLATE");
const SET_HERE = backendFieldSource("INSTANCE");

function diffRow(
  path: string,
  template: string,
  instance: string,
  source: string,
  setBy?: string,
): DiffRow {
  return {
    part: partOf(path),
    path,
    template,
    instance,
    source,
    ...(setBy === undefined ? {} : { setBy }),
  };
}

/**
 * One agent's composition beside its template, over every path `PART_OF_PATH` maps.
 *
 * `skills` is the case the diff exists to get right: both columns say the same thing and the
 * value is still one somebody set on this agent. No value carries a digit.
 */
const COMPOSITION: readonly DiffRow[] = [
  diffRow("persona", '"Answer briefly."', '"Answer briefly and name the price list."', SET_HERE, "steward-one"),
  diffRow("connectors", '["crm"]', '["crm"]', FROM_TEMPLATE),
  diffRow("skills", '["quote-draft"]', '["quote-draft"]', SET_HERE, "steward-one"),
  diffRow("tier", '"standard"', '"standard"', FROM_TEMPLATE),
  diffRow("guardrails.leash", '{"read":"auto"}', '{"read":"auto"}', FROM_TEMPLATE),
];

// ------------------------------------------------------------------------------- helpers

/** A tab's own state: what somebody typed into it. Lost if the panel is rebuilt. */
function Notepad({ tab }: { readonly tab: string }) {
  const [text, setText] = useState("");
  return (
    <textarea
      className="probe-notepad"
      aria-label={`Notes on ${tab}`}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
      }}
    />
  );
}

/** Where the router is, so a test can tell focus moving from a navigation happening. */
function WhereAmI() {
  return <output className="probe-location">{useLocation().pathname}</output>;
}

interface MountOptions {
  readonly tabs?: readonly WorkspaceTabView[];
  readonly initialTab?: string;
  readonly agent?: AgentIdentity;
}

function mountWorkspace(options: MountOptions = {}): HTMLElement {
  const { container } = render(
    <MemoryRouter initialEntries={["/somewhere"]}>
      <AgentWorkspace
        agent={options.agent ?? AGENT}
        tabs={options.tabs ?? STRIP}
        {...(options.initialTab === undefined ? {} : { initialTab: options.initialTab })}
        renderTab={(tab) => <Notepad tab={tab} />}
        dashboard={<p className="probe-dashboard">The figures.</p>}
        profile={<p className="probe-profile">The composition.</p>}
      />
      <WhereAmI />
    </MemoryRouter>,
  );
  return container;
}

function workspaceOf(container: HTMLElement): HTMLElement {
  const section = container.querySelector<HTMLElement>("section.agent-workspace");
  if (!section) {
    throw new Error("No workspace section rendered, so there is nothing to ask about.");
  }
  return section;
}

function tabButtons(container: HTMLElement): HTMLButtonElement[] {
  return [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
}

function buttonForTab(container: HTMLElement, tab: string): HTMLButtonElement {
  const label = STRIP.find((one) => one.tab === tab)?.label;
  const found = tabButtons(container).find((button) => button.textContent === label);
  if (!found) {
    throw new Error(`No tab button labelled for ${tab}.`);
  }
  return found;
}

/** The key of the one selected tab, read back through its label. Throws unless exactly one. */
function selectedKey(container: HTMLElement): string {
  const selected = tabButtons(container).filter(
    (button) => button.getAttribute("aria-selected") === "true",
  );
  if (selected.length !== 1) {
    throw new Error(`Expected exactly one selected tab and found ${selected.length}.`);
  }
  const key = STRIP.find((one) => one.label === selected[0]?.textContent)?.tab;
  if (key === undefined) {
    throw new Error("The selected tab carries a label no tab in the strip has.");
  }
  return key;
}

function paneButton(container: HTMLElement, pane: Pane): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>(".agent-panes button")].find(
    (button) => button.textContent === PANE_LABELS[pane],
  );
  if (!found) {
    throw new Error(`No pane button for ${pane}.`);
  }
  return found;
}

function notepadValue(container: HTMLElement): string {
  const notes = container.querySelector<HTMLTextAreaElement>(".probe-notepad");
  if (!notes) {
    throw new Error("The tab panel rendered no notepad.");
  }
  return notes.value;
}

/** Everything the tab key would stop on, in document order. */
function focusables(root: HTMLElement): HTMLElement[] {
  return [
    ...root.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]"),
  ].filter((element) => element.getAttribute("tabindex") !== "-1");
}

function focused(): HTMLElement {
  const active = document.activeElement;
  if (!(active instanceof HTMLElement)) {
    throw new Error("Nothing has focus.");
  }
  return active;
}

function press(key: string): boolean {
  return fireEvent.keyDown(focused(), { key });
}

function headerOf(agent: AgentIdentity): HTMLElement {
  const { container } = render(<AgentHeader agent={agent} />);
  const header = container.querySelector<HTMLElement>("header.agent-header");
  if (!header) {
    throw new Error("The header rendered no header element.");
  }
  return header;
}

function diffOf(rows: readonly DiffRow[]): HTMLElement {
  return render(<CompositionDiff rows={rows} />).container;
}

/** The sentence an empty grid says, as rendered rather than as a constant. */
function emptyGridSentence(): string {
  const columns: GridColumn<{ id: string }>[] = [{ id: "id", accessorKey: "id", header: "Id" }];
  const grid = render(
    <DataTable caption="Records" columns={columns} rows={[]} rowId={(row) => row.id} />,
  ).container;
  const sentence = grid.querySelector(".grid__empty")?.textContent ?? "";
  if (!sentence) {
    throw new Error("The grid rendered no empty sentence to compare against.");
  }
  return sentence;
}

// ------------------------------------------------------------------ the header (M39.1.2.1)

describe("the agent header", () => {
  test("the header shows the name, the role line, the owner and the lineage it was given", () => {
    // What breaks if this is deleted: every refusal below is satisfied by a header that
    // renders a name and nothing else. This is the positive sibling, and it also holds that
    // the lineage is the template and the version together, in one row.
    const header = headerOf(AGENT);

    expect(header.querySelector("h2")?.textContent).toBe(AGENT.displayName);
    expect(header.querySelector(".agent-header__role")?.textContent).toBe(AGENT.roleLine);

    const rows = [...header.querySelectorAll(".fields__row")].map((row) => ({
      label: row.querySelector("dt")?.textContent,
      value: row.querySelector("dd")?.textContent,
    }));
    expect(rows).toEqual([
      { label: OWNER_LABEL, value: AGENT.ownerId },
      { label: LINEAGE_LABEL, value: `pricing-desk ${VERSION_WORD} 4` },
    ]);
  });

  test("the avatar is letters of the name already on the screen, and is not announced", () => {
    // What breaks if this is deleted: an avatar that says something the name does not. A
    // picture would arrive as a URL, which is a second fact about the agent and a request to
    // somewhere this console does not control; letters from the first and last words add
    // nothing the reader does not already hold. Hidden, so the name is not read out twice.
    const header = headerOf(AGENT);
    const avatar = header.querySelector(".agent-header__avatar");

    expect(avatar?.textContent).toBe("QH");
    expect(avatar?.getAttribute("aria-hidden")).toBe("true");
    expect(header.querySelector("img")).toBeNull();
    expect(initials("  Mira  ")).toBe("M");
    expect(initials("ada de la mare")).toBe("AM");
  });

  test("an owner the reader may not be told contributes no element to the header", () => {
    // What breaks if this is deleted: the label stays and the value goes. "Owner" over a
    // dash, over the word unknown, or over the lock says this agent has a steward the reader
    // may not be told about, which is a fact they did not have. The label goes with the value.
    const header = headerOf(without("ownerId"));
    const text = header.textContent ?? "";

    expect([...header.querySelectorAll("dt")].map((label) => label.textContent)).toEqual([
      LINEAGE_LABEL,
    ]);
    expect(text).not.toContain(OWNER_LABEL);
    expect(text).not.toContain("steward-one");
    expect(text).not.toContain(backendLockText());
    expect(header.querySelector(".lock")).toBeNull();
    // And no element is left standing empty where the value would have been.
    const hollow = [...header.querySelectorAll("*")].filter(
      (element) => (element.textContent ?? "").trim() === "",
    );
    expect(hollow).toEqual([]);
  });

  test("a lineage the reader may not be told contributes no element, and no half of one", () => {
    // What breaks if this is deleted: a version with no template beside it, or a template
    // with no version, which says there is a template or a pin the reader may not be told.
    // That is the count of hidden things spelled out in words. The shape has no way to carry
    // half a lineage, and the rendered header has no trace of a missing one.
    const header = headerOf(without("lineage"));
    const text = header.textContent ?? "";

    expect([...header.querySelectorAll("dt")].map((label) => label.textContent)).toEqual([
      OWNER_LABEL,
    ]);
    expect(text).not.toContain(LINEAGE_LABEL);
    expect(text).not.toContain(VERSION_WORD);
    expect(text).not.toContain("pricing-desk");
    expect(text).not.toMatch(/\d/);

    const state = parseConsoleSource(STATE_MODULE);
    expect(membersOf(state, "TemplateLineage")).toEqual(["templateId", "version"]);
    expect(optionalMembersOf(state, "TemplateLineage")).toEqual([]);
    // Four optional fields since 2026-09-16: the builder joined them, under its own label,
    // sent by the route only where the Settings tab is. Optional and never required, for the
    // reason every other one here is: an absent key is a reader who was not told, and a
    // required field would make that a rendering decision instead.
    expect(optionalMembersOf(state, "AgentIdentity")).toEqual([
      "roleLine",
      "ownerId",
      "createdBy",
      "lineage",
    ]);
  });

  test("a header with nothing beyond the name renders nowhere for facts to go", () => {
    // What breaks if this is deleted: an empty definition list under the name. It is an
    // element where facts go, and two people comparing screens can read a shape. With no
    // role line, no owner and no lineage the header is the avatar and the name, and nothing.
    const header = headerOf({ agentId: AGENT.agentId, displayName: AGENT.displayName });

    expect(header.querySelector("dl, dt, dd, .agent-header__role")).toBeNull();
    expect(header.textContent).toBe(`QH${AGENT.displayName}`);
  });

  test("nothing on the header is a count, and it cannot be handed one", () => {
    // What breaks if this is deleted: "3 connectors" or "5 of 7 tabs" beside a name. The
    // fixture's only digit is the pinned version, so any other digit came from the header,
    // and the header takes one prop, so there is nowhere for a count or a reason to arrive.
    expect((headerOf(AGENT).textContent ?? "").match(/\d+/g)).toEqual(["4"]);
    expect(propNamesOf(parseConsoleSource("src/components/AgentHeader.tsx"), "AgentHeader")).toEqual([
      "agent",
    ]);
  });
});

// ------------------------------------------------------------------- the strip it is given

describe("the strip the workspace is handed", () => {
  test("the strip is drawn exactly as it was handed over, in its order, with nothing filtered again", () => {
    // What breaks if this is deleted: a second decision in the browser about which tabs a
    // person sees. `tab_strip` already narrowed the strip, and a component that filtered or
    // sorted it again would be a copy of that rule nobody keeps in step.
    expect(STRIP).toHaveLength(backendTabCount());

    const full = mountWorkspace();
    expect(tabButtons(full).map((button) => button.textContent)).toEqual(
      STRIP.map((one) => one.label),
    );
    expect(workspaceOf(full).querySelector('[role="tablist"]')?.getAttribute("aria-label")).toBe(
      TAB_STRIP_LABEL,
    );

    const reversed = [...STRIP].reverse();
    expect(tabButtons(mountWorkspace({ tabs: reversed })).map((button) => button.textContent)).toEqual(
      reversed.map((one) => one.label),
    );
  });

  test("a deep link to a tab this reader's strip does not hold opens the first tab and says nothing", () => {
    // What breaks if this is deleted: the address bar as an oracle. A link to a tab withheld
    // from this reader, a link to a tab that does not exist, and no link at all have to land
    // on one screen, or typing tab names tells somebody which ones this agent has.
    expect(STRIP.map((one) => one.tab)).toContain("memory");
    const narrowed = STRIP.filter((one) => one.tab !== "memory");

    const withheld = workspaceOf(mountWorkspace({ tabs: narrowed, initialTab: "memory" })).outerHTML;
    const unknown = workspaceOf(mountWorkspace({ tabs: narrowed, initialTab: "no-such-tab" })).outerHTML;
    const none = workspaceOf(mountWorkspace({ tabs: narrowed })).outerHTML;

    expect(withheld).toBe(none);
    expect(unknown).toBe(none);
    expect(withheld).not.toContain("memory");

    // The positive sibling: a tab the strip does hold is where the link lands.
    const wanted = narrowed[2] as WorkspaceTabView;
    expect(selectedKey(mountWorkspace({ tabs: narrowed, initialTab: wanted.tab }))).toBe(wanted.tab);
  });

  test("no attribute in the workspace is a position in the strip", () => {
    // What breaks if this is deleted: `aria-controls="agent-tab-3"`. The position of a tab
    // in a strip narrowed for this reader is the one number the strip exists not to publish,
    // and an ordinal in an id publishes it to anybody who opens the inspector. The fixture's
    // ids and keys carry no digit; the roving tabindex is the one numeric attribute, and it
    // is a zero or a minus one on every strip whatever its length.
    const section = workspaceOf(mountWorkspace());
    const numbered = [section, ...section.querySelectorAll("*")].flatMap((element) =>
      [...element.attributes]
        .filter((attribute) => attribute.name !== "tabindex" && /\d/.test(attribute.value))
        .map((attribute) => `${element.tagName}[${attribute.name}="${attribute.value}"]`),
    );
    expect(numbered).toEqual([]);
  });
});

// --------------------------------------------------------------- the right pane (M39.1.2.3)

describe("the right pane", () => {
  test("the right pane starts on the dashboard and shows the profile when asked", () => {
    // What breaks if this is deleted: every test below is satisfied by a pane that never
    // switches. Two views and no third, starting on the figures.
    expect([...PANES]).toEqual(["dashboard", "profile"]);
    expect(FIRST_PANE).toBe("dashboard");

    const container = mountWorkspace();
    expect(container.querySelector(".probe-dashboard")).not.toBeNull();
    expect(container.querySelector(".probe-profile")).toBeNull();
    expect(paneButton(container, "dashboard").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(paneButton(container, "profile"));
    expect(container.querySelector(".probe-profile")).not.toBeNull();
    expect(container.querySelector(".probe-dashboard")).toBeNull();
    expect(paneButton(container, "profile").getAttribute("aria-pressed")).toBe("true");
    expect(paneButton(container, "dashboard").getAttribute("aria-pressed")).toBe("false");
  });

  test("switching to the profile and back leaves the tab where it was, with what was typed in it", () => {
    // What breaks if this is deleted: M39.1.2.3 itself. Somebody reading a tab opens the
    // profile to check where the agent came from and comes back. If the tab moved they are
    // reading something else and nothing told them; if the panel was rebuilt, what they had
    // typed is gone. The second is the one a reducer test cannot see, so a notepad with its
    // own state sits inside the panel and is read after each switch.
    const container = mountWorkspace();
    const third = STRIP[2] as WorkspaceTabView;
    fireEvent.click(buttonForTab(container, third.tab));
    const notes = container.querySelector<HTMLTextAreaElement>(".probe-notepad");
    fireEvent.change(notes as HTMLTextAreaElement, { target: { value: "half a thought" } });

    fireEvent.click(paneButton(container, "profile"));
    expect(container.querySelector(".probe-profile")).not.toBeNull();
    expect(selectedKey(container)).toBe(third.tab);
    expect(notepadValue(container)).toBe("half a thought");
    expect(container.querySelector(".probe-notepad")).toBe(notes);

    fireEvent.click(paneButton(container, "dashboard"));
    expect(container.querySelector(".probe-dashboard")).not.toBeNull();
    expect(selectedKey(container)).toBe(third.tab);
    expect(notepadValue(container)).toBe("half a thought");
    expect(container.querySelector(".probe-notepad")).toBe(notes);
  });

  test("no sequence of actions moves the tab except selecting one, or the pane except showing one", () => {
    // What breaks if this is deleted: a reducer that resets the tab under some combination
    // nobody tried by hand, such as showing the profile twice or selecting a tab while it is
    // open. The sequences are generated from a fixed seed, so a failure reproduces.
    let seed = 7919;
    const next = (): number => {
      seed = (seed * 48271) % 2147483647;
      return seed;
    };
    const keys = [...STRIP.map((one) => one.tab), "a-tab-this-strip-does-not-hold"];

    for (let run = 0; run < 200; run += 1) {
      let state: WorkspaceState = { tab: keys[0] as string, pane: FIRST_PANE };
      let expected: WorkspaceState = state;
      const length = 1 + (next() % 30);
      for (let step = 0; step < length; step += 1) {
        const action: WorkspaceAction =
          next() % 2 === 0
            ? { kind: "select-tab", tab: keys[next() % keys.length] as string }
            : { kind: "show-pane", pane: PANES[next() % PANES.length] as Pane };
        state = reduce(state, action);
        expected =
          action.kind === "select-tab"
            ? { tab: action.tab, pane: expected.pane }
            : { tab: expected.tab, pane: action.pane };
        expect(state).toEqual(expected);
      }
    }
  });

  test("moving to another tab is a different panel, so one tab's state does not carry into the next", () => {
    // What breaks if this is deleted: the key on the panel. Without it React reconciles two
    // tabs' contents at the same position and the second tab inherits what was typed into
    // the first, which is the pane bug arriving from the other direction.
    const container = mountWorkspace();
    fireEvent.change(container.querySelector(".probe-notepad") as HTMLTextAreaElement, {
      target: { value: "about the first tab" },
    });

    fireEvent.click(buttonForTab(container, (STRIP[1] as WorkspaceTabView).tab));
    expect(notepadValue(container)).toBe("");
  });
});

// ---------------------------------------------------------------- the keyboard (M39.1.2.5)

describe("getting round the workspace from the keyboard", () => {
  test("the strip is one stop in the tab order, and that stop is the selected tab", () => {
    // What breaks if this is deleted: seven tab stops where the tabs pattern has one, or a
    // selected tab the tab key cannot reach. Checked again after an arrow, because a roving
    // tabindex that does not rove leaves the stop on a tab that is no longer selected.
    const container = mountWorkspace({ initialTab: (STRIP[3] as WorkspaceTabView).tab });
    const stops = (): HTMLButtonElement[] =>
      tabButtons(container).filter((button) => button.getAttribute("tabindex") !== "-1");

    expect(stops()).toHaveLength(1);
    expect(stops()[0]?.getAttribute("tabindex")).toBe("0");
    expect(stops()[0]?.getAttribute("aria-selected")).toBe("true");

    (stops()[0] as HTMLButtonElement).focus();
    press("ArrowRight");
    expect(stops()).toHaveLength(1);
    expect(stops()[0]).toBe(focused());
  });

  test("the right arrow moves focus to the next tab and opens it, wrapping from the last to the first", () => {
    // What breaks if this is deleted: arrows that select without moving focus, which leaves
    // the keyboard on a tab that is not the open one, or a strip with an end the arrows fall
    // off. Wrapping is what lets somebody move through a strip without knowing its length.
    const container = mountWorkspace();
    (tabButtons(container)[0] as HTMLButtonElement).focus();

    for (let step = 1; step <= STRIP.length; step += 1) {
      expect(press("ArrowRight")).toBe(false);
      const expected = STRIP[step % STRIP.length] as WorkspaceTabView;
      expect(focused().textContent).toBe(expected.label);
      expect(selectedKey(container)).toBe(expected.tab);
      expect(container.querySelector('[role="tabpanel"]')?.getAttribute("aria-labelledby")).toBe(
        focused().id,
      );
    }
  });

  test("the left arrow moves back, wrapping from the first to the last", () => {
    // What breaks if this is deleted: a strip that can only be walked one way, or a left
    // arrow on the first tab that goes nowhere, which reads as the keyboard having stopped.
    const container = mountWorkspace();
    (tabButtons(container)[0] as HTMLButtonElement).focus();

    press("ArrowLeft");
    const last = STRIP[STRIP.length - 1] as WorkspaceTabView;
    expect(focused().textContent).toBe(last.label);
    expect(selectedKey(container)).toBe(last.tab);

    press("ArrowLeft");
    const beforeLast = STRIP[STRIP.length - 2] as WorkspaceTabView;
    expect(focused().textContent).toBe(beforeLast.label);
  });

  test("home and end reach the first and the last tab", () => {
    // What breaks if this is deleted: the two keys the tabs pattern promises, on a strip of
    // seven, where walking the length of it with an arrow is the alternative.
    const container = mountWorkspace({ initialTab: (STRIP[2] as WorkspaceTabView).tab });
    buttonForTab(container, (STRIP[2] as WorkspaceTabView).tab).focus();

    press("End");
    expect(selectedKey(container)).toBe((STRIP[STRIP.length - 1] as WorkspaceTabView).tab);
    expect(focused().textContent).toBe((STRIP[STRIP.length - 1] as WorkspaceTabView).label);

    press("Home");
    expect(selectedKey(container)).toBe((STRIP[0] as WorkspaceTabView).tab);
    expect(focused().textContent).toBe((STRIP[0] as WorkspaceTabView).label);
  });

  test("escape moves focus to the way back to the roster and does not follow it", () => {
    // What breaks if this is deleted: the way back from the strip, or a key handler that
    // navigates. Focus is reversible and navigation is not, and a handler that navigated
    // would take Escape away from every dialog and menu ever nested inside the workspace.
    const container = mountWorkspace();
    const where = (): string => container.querySelector(".probe-location")?.textContent ?? "";
    const before = where();
    (tabButtons(container)[0] as HTMLButtonElement).focus();

    expect(press("Escape")).toBe(false);

    expect(focused().tagName).toBe("A");
    expect(focused().textContent).toBe(BACK_TO_ROSTER);
    expect(focused().getAttribute("href")).toBe(ROSTER_ADDRESS);
    expect(where()).toBe(before);
  });

  test("the way back comes before the strip, so shift and tab reach it with no handler at all", () => {
    // What breaks if this is deleted: the link drifting below the strip, where the only way
    // back without a mouse is a key somebody has to know about. First in the workspace, and
    // the selected tab is the very next stop.
    const container = mountWorkspace();
    const stops = focusables(workspaceOf(container));

    expect(stops[0]?.textContent).toBe(BACK_TO_ROSTER);
    expect(stops[1]?.getAttribute("aria-selected")).toBe("true");
  });

  test("a key the strip has no use for is left to the browser", () => {
    // What breaks if this is deleted: a handler that swallows every key. Tab would stop
    // leaving the strip, and Enter and Space would stop reaching the button they belong to.
    const container = mountWorkspace();
    (tabButtons(container)[1] as HTMLButtonElement).focus();

    for (const key of ["Tab", "Enter", " ", "a", "ArrowDown", "ArrowUp"]) {
      expect(press(key)).toBe(true);
    }
    expect(selectedKey(container)).toBe((STRIP[0] as WorkspaceTabView).tab);
  });

  test("the roster is where every agent's address is, as the Python side spells it", () => {
    // What breaks if this is deleted: a way back to an address wrong by one character.
    // `DEEP_LINK_PREFIX` is where every agent is addressed and the roster is that prefix
    // without the separator that introduces one agent; read from the module that owns it.
    const prefix = backendDeepLinkPrefix();
    expect(AGENT_ADDRESS_PREFIX).toBe(prefix);
    expect(`${ROSTER_ADDRESS}/`).toBe(prefix);
  });
});

// -------------------------------------------------------- the composition diff (M39.1.1.5)

describe("the composition diff", () => {
  test("each path is shown with both sides at once, under the part it supplies, in the order it arrived", () => {
    // What breaks if this is deleted: every refusal below is satisfied by a diff that draws
    // nothing. Both values sit in their own cells in one row, the template's first, and the
    // rows are grouped under the parts `PART_OF_PATH` says each path supplies.
    const container = diffOf(COMPOSITION);

    expect([...container.querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      PATH_COLUMN,
      TEMPLATE_COLUMN,
      INSTANCE_COLUMN,
      SOURCE_COLUMN,
    ]);
    expect(
      [...container.querySelectorAll('th[scope="rowgroup"]')].map((cell) => cell.textContent),
    ).toEqual(COMPOSITION.map((row) => row.part));

    const drawn = [...container.querySelectorAll("tr.composition-diff__row")].map((row) => {
      const cells = [...row.querySelectorAll("th, td")];
      return {
        path: cells[0]?.textContent,
        template: cells[1]?.textContent,
        instance: cells[2]?.textContent,
        source: cells[3]?.querySelector(".chip")?.textContent,
        setBy: cells[3]?.querySelector("code")?.textContent,
      };
    });
    expect(drawn).toEqual(
      COMPOSITION.map((row) => ({
        path: row.path,
        template: row.template,
        instance: row.instance,
        source: row.source,
        setBy: row.setBy,
      })),
    );
  });

  test("rows of one part that arrived apart are drawn under one heading, in arrival order", () => {
    // What breaks if this is deleted: a part heading repeated for every row, or rows sorted
    // into an order this file chose. The order is `MANIFEST_PATHS` order when the rows come
    // from `brain.agents.upgrade`, so the same review reads the same way twice running.
    const persona = diffRow("persona", '"a"', '"b"', SET_HERE);
    const skills = diffRow("skills", '["x"]', '["x"]', FROM_TEMPLATE);
    const alsoPersona = { ...persona, path: "persona.greeting" };

    expect(groupByPart([persona, skills, alsoPersona])).toEqual([
      { part: persona.part, rows: [persona, alsoPersona] },
      { part: skills.part, rows: [skills] },
    ]);
  });

  test("a value set on this agent is marked by the source it carries, even where both sides agree", () => {
    // What breaks if this is deleted: divergence decided by comparing the two columns. It is
    // right on every row but the one `brain.agents.upgrade` names, where the template happens
    // to say what this agent already set: the values match and the path is still a local
    // decision, and the next version moves it silently if it is read as untouched.
    expect(SET_ON_THIS_AGENT).toBe(SET_HERE);

    const container = diffOf([
      diffRow("skills", '["quote-draft"]', '["quote-draft"]', SET_HERE, "steward-one"),
      diffRow("persona", '"Answer briefly."', '"Answer at length."', FROM_TEMPLATE),
    ]);
    const marked = [...container.querySelectorAll("tr.composition-diff__row")].map((row) =>
      row.classList.contains("composition-diff__row--local"),
    );
    expect(marked).toEqual([true, false]);
  });

  test("a source word nobody has defined is shown as itself and marks nothing", () => {
    // What breaks if this is deleted: an unknown word treated as a local edit, which marks a
    // row as set on this agent on no evidence at all. The word is still drawn, so a new
    // member on the Python side is visible rather than silently dropped.
    const container = diffOf([diffRow("persona", '"a"', '"b"', "inherited-from-department")]);
    const row = container.querySelector("tr.composition-diff__row");

    expect(row?.querySelector(".chip")?.textContent).toBe("inherited-from-department");
    expect(row?.classList.contains("composition-diff__row--local")).toBe(false);
  });

  test("a path whose value is withheld is not a row, and leaves no heading, cell or marker behind", () => {
    // What breaks if this is deleted: "leash: changed" with the value left out, which tells
    // the reader that a value exists, that somebody changed it, and that they may not have
    // it. The shape requires both sides, and a diff without the path is the same markup as
    // a diff that never had it, down to the part heading its row would have sat under.
    const state = parseConsoleSource(STATE_MODULE);
    expect(optionalMembersOf(state, "DiffRow")).toEqual(["setBy"]);

    const withheld = COMPOSITION.filter((row) => row.path !== "guardrails.leash");
    const container = diffOf(withheld);
    const markup = container.innerHTML;

    expect(markup).not.toContain("guardrails.leash");
    expect(markup).not.toContain(partOf("guardrails.leash"));
    expect(markup).toBe(diffOf(COMPOSITION.slice(0, 4)).innerHTML);
  });

  test("an empty diff says what an empty grid says, and draws no table", () => {
    // What breaks if this is deleted: a diff that explains itself. Empty because nothing was
    // set and empty because every row was withheld are one event; the sentence is compared
    // with the grid's as rendered, so either screen saying something of its own fails here.
    const container = diffOf([]);

    expect(container.querySelector(".composition-diff__empty")?.textContent).toBe(emptyGridSentence());
    expect(container.querySelector("table, caption")).toBeNull();
  });

  test("nothing around the diff counts, and the diff cannot be told what it came from", () => {
    // What breaks if this is deleted: "5 paths" in a caption, or a caption naming the
    // template for a reader who may see the paths and not the lineage. The fixture carries no
    // digit and the component takes one prop, so neither a count nor a template can arrive.
    const container = diffOf(COMPOSITION);

    expect(container.querySelector("caption")?.textContent).toBe(DIFF_CAPTION);
    expect(container.textContent ?? "").not.toMatch(/\d/);
    expect(
      propNamesOf(parseConsoleSource("src/components/CompositionDiff.tsx"), "CompositionDiff"),
    ).toEqual(["rows"]);
  });
});

// ------------------------------------------------------------- what the shapes have room for

describe("what the workspace's shapes have room for", () => {
  test("no shape the workspace is drawn from has a field for what was left out", () => {
    // What breaks if this is deleted: `hiddenCount` added to a shape by somebody making a
    // screen better. The names are read from `brain.ops.jobs.NAMES_THAT_WOULD_BE_A_HIDDEN_
    // COUNT`, so a name added there tightens this on the same day.
    const forbidden = new Set(backendHiddenCountNames());
    const state = parseConsoleSource(STATE_MODULE);
    const found = ["AgentIdentity", "TemplateLineage", "WorkspaceTabView", "DiffRow", "WorkspaceState"]
      .flatMap((name) => membersOf(state, name).map((member) => `${name}.${member}`))
      .filter((qualified) => forbidden.has(asPythonName(qualified.split(".")[1] ?? "")));

    expect(found).toEqual([]);
  });

  test("the check for a hidden count finds one when a shape has it", () => {
    // What breaks if this is deleted: the test above passing because the check can find
    // nothing at all, for example if the member names stopped converting to the Python
    // spelling. A shape written to leak is handed to the same check and must be caught.
    const forbidden = new Set(backendHiddenCountNames());
    const leaky = ts.createSourceFile(
      "leaky.ts",
      "interface Leaky { readonly label: string; readonly hiddenCount: number; readonly total: number }",
      ts.ScriptTarget.ES2022,
      true,
      ts.ScriptKind.TS,
    );

    expect(membersOf(leaky, "Leaky").filter((member) => forbidden.has(asPythonName(member)))).toEqual([
      "hiddenCount",
      "total",
    ]);
  });
});
