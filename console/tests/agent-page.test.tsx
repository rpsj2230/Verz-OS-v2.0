/**
 * The agent page: where the workspace is reachable, what it asks for, and how an answer is
 * read.
 *
 * `tests/agent-workspace.test.tsx` holds the four leaves against the components, handed their
 * shapes directly. This holds the half between the API and those shapes, which is where a
 * withheld field most easily turns back into a visible one. A reader that carried a null as a
 * value, kept a template with no version, or kept a diff row with one side filled in would
 * hand a renderer something to draw where the rule says nothing, and every component test
 * would still pass.
 *
 * **Reachable means through the application's own route table.** The page is mounted at the
 * address `brain.console.workspace.deep_link` spells, on a memory router over `routes` from
 * `src/App.tsx`, signed in through the real session modules and answered by a stand-in API. A
 * test that rendered the page component directly would pass with the route deleted.
 *
 * **Withheld and absent are compared as markup.** Each refusal renders the variants a route
 * could plausibly send for "not told" (the key missing, null, empty, the wrong type) and
 * asserts they are one string, and each has a sibling proving the field reaches the screen
 * when it is sent.
 *
 * **`brain.agent_routes` serves the address the page asks, and the reader is checked against
 * the route's declared response.** Until 2026-09-14 one test here asserted no route did, and
 * was written to go red on the day that stopped being true. It did, and the test that replaced
 * it reads every wire name off the document the route produces.
 *
 * Task ids: M39.1.2.1, M39.1.2.3, M39.1.2.5, M39.1.1.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { AgentHeader, LINEAGE_LABEL, OWNER_LABEL, VERSION_WORD } from "../src/components/AgentHeader";
import { PANE_LABELS } from "../src/components/AgentWorkspace";
import { CompositionDiff } from "../src/components/CompositionDiff";
import { tabAddress, type Pane } from "../src/components/agentWorkspaceState";
import {
  readAgentWorkspace,
  type AgentWorkspaceAnswer,
} from "../src/pages/agentQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  asPythonName,
  backendDeepLinkPrefix,
  backendFieldSource,
  backendHiddenCountNames,
  backendPartOfPath,
  backendTabOrder,
  membersOf,
} from "./support/agentWorkspace";
import {
  apiDocument,
  declaredProperty,
  declaredPropertyNames,
  declaredResponseSchema,
} from "./support/openapi";
import { backendEnumMembers, backendModelFields, backendPublicMessages } from "./support/python";
import { readRepoFile } from "./support/repo";
import { parseConsoleSource, staticImportGraph } from "./support/typescript";

const WORKSPACE_MODULE = "src/brain/console/workspace.py";
const MODEL_MODULE = "src/brain/agents/model.py";
const TEMPLATE_MODULE = "src/brain/agents/template.py";
const CONSOLE_ORIGIN = "https://console.test";
const AGENTS_API = "/api/v1/agents/";
const WORKSPACE_ROUTE = "/api/v1/agents/{agent_id}/workspace";

/**
 * Transform the split route once, before anything is timed. The first mount of a code-split
 * page in a file is the first time Vite transforms it, which is not the property under test and
 * reads as a flake when it lands inside a `waitFor`. The records suite does the same.
 */
beforeAll(async () => {
  await import("../src/pages/Agent");
}, 60_000);

// ------------------------------------------------------------------------------- fixtures

function capitalised(word: string): string {
  return `${word.slice(0, 1).toLocaleUpperCase("en-GB")}${word.slice(1)}`;
}

/** The part a manifest path supplies, in the spelling `brain.console.workspace` serialises. */
function partOf(path: string): string {
  const member = backendPartOfPath()[path];
  const value = member === undefined ? undefined : backendEnumMembers(WORKSPACE_MODULE, "Part")[member];
  if (value === undefined) {
    throw new Error(`PART_OF_PATH does not map ${path} to a Part value; the fixture is stale.`);
  }
  return value;
}

const SET_HERE = backendFieldSource("INSTANCE");
const FROM_TEMPLATE = backendFieldSource("TEMPLATE");

/** One agent on the wire, with every fact the header can show. The only digit is the version. */
function agentWire(agentId = "quote-helper", displayName = "Quote Helper"): Record<string, unknown> {
  return {
    agent_id: agentId,
    display_name: displayName,
    summary: "Drafts a first answer to a pricing question.",
    owner_id: "steward-one",
    template_id: "pricing-desk",
    template_version: 4,
  };
}

/** A whole strip on the wire, in `TABS` order and spelled with the `Tab` enum's values. */
function stripWire(): Record<string, unknown>[] {
  const values = backendEnumMembers(WORKSPACE_MODULE, "Tab");
  return backendTabOrder().map((member) => {
    const tab = values[member];
    if (tab === undefined) {
      throw new Error(`TABS names Tab.${member}, which the Tab enum does not declare.`);
    }
    return { tab, label: capitalised(tab), purpose: `What the ${tab} tab is for.` };
  });
}

/** Three composition rows on the wire, one of them set here with both sides agreeing. */
function compositionWire(): Record<string, unknown>[] {
  return [
    {
      part: partOf("persona"),
      path: "persona",
      template: '"Answer briefly."',
      instance: '"Answer briefly and name the price list."',
      source: SET_HERE,
      set_by: "steward-one",
    },
    {
      part: partOf("skills"),
      path: "skills",
      template: '["quote-draft"]',
      instance: '["quote-draft"]',
      source: SET_HERE,
      set_by: "steward-one",
    },
    {
      part: partOf("tier"),
      path: "tier",
      template: '"standard"',
      instance: '"standard"',
      source: FROM_TEMPLATE,
    },
  ];
}

function body(agent: Record<string, unknown> = agentWire()): Record<string, unknown> {
  return { agent, tabs: stripWire(), composition: compositionWire() };
}

function without(record: Record<string, unknown>, ...keys: string[]): Record<string, unknown> {
  const copy = { ...record };
  for (const key of keys) {
    delete copy[key];
  }
  return copy;
}

function read(payload: unknown): AgentWorkspaceAnswer {
  const answer = readAgentWorkspace(payload);
  if (answer === null) {
    throw new Error("The reader found no agent in a body that has one.");
  }
  return answer;
}

function headerMarkup(agent: Record<string, unknown>): string {
  return render(<AgentHeader agent={read(body(agent)).agent} />).container.innerHTML;
}

function diffMarkup(rows: unknown): string {
  return render(<CompositionDiff rows={read({ agent: agentWire(), composition: rows }).composition} />)
    .container.innerHTML;
}

// ------------------------------------------------------------------------------- mounting

interface Answer {
  readonly status?: number;
  readonly body: unknown;
  readonly traceId?: string;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

/**
 * The whole console at one address, signed in, with the stand-in API answering for the agents
 * named in `answers` and for nothing else.
 */
async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      const asked = new URL(url, CONSOLE_ORIGIN).pathname;
      if (!asked.startsWith(AGENTS_API)) {
        return null;
      }
      const agentId = decodeURIComponent(asked.slice(AGENTS_API.length).split("/")[0] ?? "");
      const answer = answers[agentId];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: {
          "content-type": "application/json",
          ...(answer.traceId ? { "x-trace-id": answer.traceId } : {}),
        },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('p.note[role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp, router };
}

/** Every request the console made about an agent, as URLs. */
function agentRequests(idp: FakeIdp): URL[] {
  return idp.urls
    .map((url) => new URL(url, CONSOLE_ORIGIN))
    .filter((url) => url.pathname.startsWith(AGENTS_API));
}

function selectedLabel(container: HTMLElement): string {
  return container.querySelector('[role="tab"][aria-selected="true"]')?.textContent ?? "";
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

// ------------------------------------------------------------------------- reachability

describe("where the workspace is reachable", () => {
  test("the address of one tab of one agent renders that agent's workspace, on that tab", async () => {
    // What breaks if this is deleted: the workspace with no way in. The components are held
    // by their own tests whether or not anything mounts them, so this is the test that fails
    // when the route is removed. The address is checked against the Python spelling first,
    // so the route answers the link `deep_link` would put in an alert.
    expect(readRepoFile(WORKSPACE_MODULE)).toMatch(
      /^ {4}return f"\{DEEP_LINK_PREFIX\}\{agent_id\}\/\{key\.value\}"$/m,
    );
    expect(tabAddress("quote-helper", "memory")).toBe(`${backendDeepLinkPrefix()}quote-helper/memory`);

    const { container } = await consoleAt(tabAddress("quote-helper", "memory"), {
      "quote-helper": { body: body() },
    });
    const { AGENT_HEADING } = await import("../src/pages/Agent");

    expect(container.querySelector("h1")?.textContent).toBe(AGENT_HEADING);
    expect(container.querySelector(".agent-header h2")?.textContent).toBe("Quote Helper");
    expect(selectedLabel(container)).toBe("Memory");
  });

  test("the address of an agent with no tab opens the first tab its strip holds", async () => {
    // What breaks if this is deleted: the bare agent address, which is the one a roster links
    // to, rendering nothing selected or the not-found page.
    const { container } = await consoleAt("/agents/quote-helper", {
      "quote-helper": { body: body() },
    });

    expect(selectedLabel(container)).toBe(stripWire()[0]?.["label"]);
  });

  test("the page asks the API about the agent in the address, once, and not about the tab", async () => {
    // What breaks if this is deleted: a page asking about a different agent from the one
    // its address names, which sends two people sharing a link to two different questions, or
    // a request carrying the tab, which is a second question with the same answer.
    const { idp } = await consoleAt(tabAddress("quote-helper", "memory"), {
      "quote-helper": { body: body() },
    });
    const asked = agentRequests(idp);

    expect(asked.map((url) => `${url.pathname}${url.search}`)).toEqual([
      "/api/v1/agents/quote-helper/workspace",
    ]);
  });

  test("the profile pane on the page is the composition diff the API sent", async () => {
    // What breaks if this is deleted: a page that mounts the frame and not the diff, which
    // passes every test above because none of them opens the profile.
    const { container } = await consoleAt("/agents/quote-helper", {
      "quote-helper": { body: body() },
    });
    fireEvent.click(paneButton(container, "profile"));

    expect(
      [...container.querySelectorAll("tr.composition-diff__row th code")].map((cell) => cell.textContent),
    ).toEqual(["persona", "skills", "tier"]);
  });

  test("the workspace and its stylesheet are not in the first response, and the page reaches both", () => {
    // What breaks if this is deleted: the split, silently. A static import of the page in
    // `App.tsx` puts three components and a stylesheet in front of everybody who never opens
    // an agent. The sibling half proves the page really reaches them, so the refusal is not
    // satisfied by a page that stopped importing the workspace at all.
    const workspaceFiles = [
      "src/pages/Agent.tsx",
      "src/components/AgentWorkspace.tsx",
      "src/components/AgentHeader.tsx",
      "src/components/CompositionDiff.tsx",
      "src/styles/agent-workspace.css",
    ];
    const entry = new Set(staticImportGraph("src/main.tsx").files);
    expect(workspaceFiles.filter((file) => entry.has(file))).toEqual([]);

    const page = new Set(staticImportGraph("src/pages/Agent.tsx").files);
    expect(workspaceFiles.filter((file) => !page.has(file))).toEqual([]);
  });

  test("the route the page asks is declared, and every name the reader takes is a name it sends", () => {
    // What breaks if this is deleted: a reader and the route drifting apart on a name, which
    // renders an agent with a fact silently missing and no test anywhere red. Every name is
    // read off the declared response of the route this page calls. The sets are exact, so the
    // two names the route deliberately withholds, the builder and who set a value, are a red
    // test the day either is sent rather than a header that quietly grew a fact.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths.filter((path) => path.startsWith(AGENTS_API))).toContain(WORKSPACE_ROUTE);

    const workspace = declaredResponseSchema(WORKSPACE_ROUTE, "get");
    expect(declaredPropertyNames(workspace)).toEqual(["agent", "composition", "tabs"]);
    expect(declaredPropertyNames(declaredProperty(workspace, "agent"))).toEqual([
      "agent_id",
      "display_name",
      "owner_id",
      "summary",
      "template_id",
      "template_version",
    ]);
    expect(declaredPropertyNames(declaredProperty(workspace, "tabs"))).toEqual(["label", "purpose", "tab"]);
    const rows = declaredPropertyNames(declaredProperty(workspace, "composition"));
    expect(rows).toEqual(["instance", "part", "path", "source", "template"]);
    expect(rows).not.toContain("set_by");
    expect(declaredPropertyNames(declaredProperty(workspace, "agent"))).not.toContain("created_by");
  });
});

// ------------------------------------------------------------------- what an answer becomes

describe("what an answer becomes", () => {
  test("every wire name the reader shares with the Python side is a field that side declares", () => {
    // What breaks if this is deleted: a reader and a model that stopped agreeing about a
    // name, which renders an agent with a fact silently missing. Each name is read off the
    // model that owns it, including `created_by`, the field the owner is deliberately not.
    const origins: readonly (readonly [string, string, string])[] = [
      ["agent_id", MODEL_MODULE, "AgentRecord"],
      ["display_name", MODEL_MODULE, "AgentRecord"],
      ["created_by", MODEL_MODULE, "AgentRecord"],
      ["owner_id", MODEL_MODULE, "AgentAudience"],
      ["summary", TEMPLATE_MODULE, "ManifestIdentity"],
      ["template_id", TEMPLATE_MODULE, "TemplateInstance"],
      ["template_version", TEMPLATE_MODULE, "TemplateInstance"],
      ["tab", WORKSPACE_MODULE, "WorkspaceTab"],
      ["purpose", WORKSPACE_MODULE, "WorkspaceTab"],
      ["read", WORKSPACE_MODULE, "WorkspaceTab"],
      ["source", TEMPLATE_MODULE, "FieldOwner"],
      ["set_by", TEMPLATE_MODULE, "FieldOwner"],
    ];
    for (const [name, module, model] of origins) {
      expect(backendModelFields(module, model), `${model}.${name}`).toContain(name);
    }
  });

  test("everything the API sends about the agent, its strip and its composition is carried", () => {
    // What breaks if this is deleted: every refusal below is satisfied by a reader that
    // returns nothing. This is the positive sibling for all of them.
    expect(read(body())).toEqual({
      agent: {
        agentId: "quote-helper",
        displayName: "Quote Helper",
        roleLine: "Drafts a first answer to a pricing question.",
        ownerId: "steward-one",
        lineage: { templateId: "pricing-desk", version: 4 },
      },
      tabs: stripWire(),
      composition: [
        {
          part: partOf("persona"),
          path: "persona",
          template: '"Answer briefly."',
          instance: '"Answer briefly and name the price list."',
          source: SET_HERE,
          setBy: "steward-one",
        },
        {
          part: partOf("skills"),
          path: "skills",
          template: '["quote-draft"]',
          instance: '["quote-draft"]',
          source: SET_HERE,
          setBy: "steward-one",
        },
        {
          part: partOf("tier"),
          path: "tier",
          template: '"standard"',
          instance: '"standard"',
          source: FROM_TEMPLATE,
        },
      ],
    });
  });

  test("an owner that was withheld, null, empty or not a string is one header, with no owner in it", () => {
    // What breaks if this is deleted: a reader that carries `null` or `""` as an owner, which
    // hands the header something to draw a label over. A route that says "not told" with a
    // null and a route that leaves the key out must produce the same screen.
    const variants = [
      without(agentWire(), "owner_id"),
      { ...agentWire(), owner_id: null },
      { ...agentWire(), owner_id: "" },
      { ...agentWire(), owner_id: "   " },
      { ...agentWire(), owner_id: 42 },
    ].map(headerMarkup);

    expect(new Set(variants).size).toBe(1);
    expect(variants[0]).not.toContain(OWNER_LABEL);
    expect(headerMarkup(agentWire())).toContain("steward-one");
  });

  test("a template without its version, or a version without its template, is no lineage at all", () => {
    // What breaks if this is deleted: half a lineage on the screen, "version 4" under a
    // template the reader may not be told, which is the count of hidden things in words.
    const neither = headerMarkup(without(agentWire(), "template_id", "template_version"));
    const halves = [
      without(agentWire(), "template_version"),
      without(agentWire(), "template_id"),
      { ...agentWire(), template_version: null },
      { ...agentWire(), template_version: "4" },
      { ...agentWire(), template_version: 0 },
      { ...agentWire(), template_version: 4.5 },
      { ...agentWire(), template_id: "" },
    ].map(headerMarkup);

    for (const markup of halves) {
      expect(markup).toBe(neither);
    }
    expect(neither).not.toContain(LINEAGE_LABEL);
    expect(neither).not.toContain(VERSION_WORD);
    expect(neither).not.toContain("pricing-desk");

    const both = headerMarkup(agentWire());
    expect(both).toContain(LINEAGE_LABEL);
    expect(both).toContain("pricing-desk");
  });

  test("a composition row missing either side is not a row, and the diff is the one without it", () => {
    // What breaks if this is deleted: "skills, set here" with this agent's value blank, which
    // tells the reader the path exists, that somebody set it, and that they may not see what
    // to. Every way a side can be missing is tried, and each diff must be byte for byte the
    // diff of the rows that carried both.
    const complete = compositionWire();
    const withheldSides = [
      without(compositionWire()[1] as Record<string, unknown>, "instance"),
      { ...(compositionWire()[1] as Record<string, unknown>), template: null },
      { ...(compositionWire()[1] as Record<string, unknown>), instance: "" },
      { ...(compositionWire()[1] as Record<string, unknown>), template: ["quote-draft"] },
    ];

    const expected = diffMarkup([complete[0], complete[2]]);
    for (const withheld of withheldSides) {
      const markup = diffMarkup([complete[0], withheld, complete[2]]);
      expect(markup).toBe(expected);
      expect(markup).not.toContain("quote-draft");
    }
    expect(diffMarkup(complete)).toContain("quote-draft");
  });

  test("the owner shown is the steward, and the builder is never shown in the steward's place", () => {
    // What breaks if this is deleted: a fallback from the steward to whoever built the agent,
    // which puts a name on exactly the agents whose steward was withheld, and puts the wrong
    // name there: `brain.agents.model` keeps the two apart because they stop being one person.
    const both = headerMarkup({ ...agentWire(), created_by: "the-builder" });
    expect(both).toContain("steward-one");
    expect(both).not.toContain("the-builder");

    const builderOnly = headerMarkup({ ...without(agentWire(), "owner_id"), created_by: "the-builder" });
    expect(builderOnly).not.toContain("the-builder");
    expect(builderOnly).not.toContain(OWNER_LABEL);
  });

  test("a count or a capability the API sends reaches nothing on the page", async () => {
    // What breaks if this is deleted: "showing 5 of 7 tabs", or a tab's required capability
    // in an attribute. A route serialising `WorkspaceTab` whole would send its `read`, which
    // names the grant each tab needs, and a total beside a narrowed strip is the subtraction.
    const leaky = {
      agent: { ...agentWire(), hidden_count: 4700, created_by: "the-builder" },
      tabs: stripWire().map((tab) => ({
        ...tab,
        read: { screen: `agent_workspace.${String(tab["tab"])}`, requires: "read:memory" },
      })),
      composition: compositionWire().map((row) => ({ ...row, omitted: 4700 })),
      total: 4700,
      hidden: 4700,
      of_total: "4700",
    };
    expect(JSON.stringify(read(leaky))).not.toMatch(/4700|read:memory|agent_workspace|the-builder/);

    const { container } = await consoleAt("/agents/quote-helper", { "quote-helper": { body: leaky } });
    fireEvent.click(paneButton(container, "profile"));
    expect(container.innerHTML).not.toMatch(/4700|read:memory|agent_workspace\.|the-builder/);
  });

  test("the answer the page holds has no field for what was left out", () => {
    // What breaks if this is deleted: `hiddenTabs` added to the answer to make a heading
    // better. The names are `brain.ops.jobs`' own list, read rather than copied.
    const forbidden = new Set(backendHiddenCountNames());
    const members = membersOf(parseConsoleSource("src/pages/agentQuery.ts"), "AgentWorkspaceAnswer");

    expect(members).toEqual(["agent", "tabs", "composition"]);
    expect(members.filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });

  test("an answer with no readable agent draws no workspace and composes no sentence about it", async () => {
    // What breaks if this is deleted: a body that is not a workspace rendered as an agent with
    // no name, or explained in a sentence nobody sent. The sibling shows the least a readable
    // answer can be.
    for (const unreadable of [
      null,
      [],
      {},
      { agent: "quote-helper" },
      { agent: { agent_id: "quote-helper" } },
      { agent: { display_name: "Quote Helper" } },
    ]) {
      expect(readAgentWorkspace(unreadable)).toBeNull();
    }
    expect(readAgentWorkspace({ agent: { agent_id: "quote-helper", display_name: "Quote Helper" } })).toEqual({
      agent: { agentId: "quote-helper", displayName: "Quote Helper" },
      tabs: [],
      composition: [],
    });

    const { container } = await consoleAt("/agents/quote-helper", { "quote-helper": { body: {} } });
    expect(container.querySelector(".agent-workspace")).toBeNull();
    expect(container.querySelector(".notice")).toBeNull();
  });
});

// --------------------------------------------------------------------- what a failure is

describe("what a failure looks like", () => {
  test("an agent the API will not describe is the API's own sentence, whichever kind of 404 it was", async () => {
    // What breaks if this is deleted: a page that tells a refusal from an address nothing
    // serves. A withheld agent answers with the DENIED body and an unknown agent, or today any
    // agent, answers with a bare 404; both must reach the screen as the one sentence the
    // taxonomy gives DENIED and ABSENT, with no workspace and no page of the console's own.
    const messages = backendPublicMessages();
    const sentence = messages["DENIED"];
    expect(sentence).toBeTruthy();
    expect(messages["ABSENT"]).toBe(sentence);

    const refused = await consoleAt("/agents/quote-helper", {
      "quote-helper": { status: 404, body: { message: sentence }, traceId: "trace-refused" },
    });
    const unserved = await consoleAt("/agents/quote-helper", {
      "quote-helper": { status: 404, body: { detail: "Not Found" } },
    });

    for (const { container } of [refused, unserved]) {
      expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
      expect(container.querySelector(".agent-workspace, .agent-header")).toBeNull();
      expect(container.textContent).not.toContain("No such page");
    }
    expect(refused.container.querySelector(".notice__trace code")?.textContent).toBe("trace-refused");
  });
});

// ------------------------------------------------------------ moving between agents and tabs

describe("moving between agents and tabs", () => {
  const answers: Record<string, Answer> = {
    "quote-helper": { body: body() },
    "rota-helper": { body: body(agentWire("rota-helper", "Rota Helper")) },
  };

  test("another agent at the same route starts from its own first tab", async () => {
    // What breaks if this is deleted: one agent's open tab turning up on the next agent opened
    // from the same page, which is a workspace saying something about an agent that belongs
    // to a different one.
    const { container, router } = await consoleAt(tabAddress("quote-helper", "memory"), answers);
    expect(selectedLabel(container)).toBe("Memory");

    await act(async () => {
      await router.navigate("/agents/rota-helper");
    });
    await waitFor(() => {
      expect(container.querySelector(".agent-header h2")?.textContent).toBe("Rota Helper");
    });
    expect(selectedLabel(container)).toBe(stripWire()[0]?.["label"]);
  });

  test("following a link to another tab of the open agent lands on that tab without asking again", async () => {
    // What breaks if this is deleted: the deep link from an alert opening on whatever tab was
    // already showing, because the workspace was reused rather than told where to land. And
    // it lands without a second request, because the tab is the console's state, not a
    // question to the API.
    const { container, router, idp } = await consoleAt(tabAddress("quote-helper", "memory"), answers);

    await act(async () => {
      await router.navigate(tabAddress("quote-helper", "people"));
    });
    await waitFor(() => {
      expect(selectedLabel(container)).toBe("People");
    });
    expect(agentRequests(idp)).toHaveLength(1);
  });
});
