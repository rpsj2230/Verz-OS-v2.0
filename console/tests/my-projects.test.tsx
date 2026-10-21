/**
 * The projects card in My workspace, and the project choice on Ask.
 *
 * Mounted on their own, for the reason `tests/my-workspace-page.test.tsx` gives. The failures worth
 * testing look like the page working: a project made with an empty or untidy name, a project made
 * on an install that has the switch off, a document marked as unreadable, and a question that
 * names a project the person did not choose.
 *
 * Task ids: M40.7.7
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  MAKE_LABEL,
  NOT_SWITCHED_ON,
  NOTHING_IN_PROJECTS,
  PROJECTS_NOTE,
  PUT_AWAY_CONSEQUENCE,
  PUT_AWAY_LABEL,
  TAKE_OUT_LABEL,
} from "../src/components/MyProjects";
import { NO_PROJECT, PROJECT_LABEL, PROJECT_NOTE } from "../src/pages/AskProject";
import { askBody } from "../src/pages/askQuery";
import { nameBody, projectField } from "../src/pages/myProjectsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";
const PROJECT = "3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b";

beforeAll(async () => {
  await import("../src/components/MyProjects");
}, 60_000);

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const LISTED = (on: boolean) => ({
  projects: [{ project_id: PROJECT, name: "Quarter plan", created_at: "2019-03-01T09:00:00Z" }],
  switched_on: on,
});

const DETAIL = {
  project_id: PROJECT,
  name: "Quarter plan",
  created_at: "2019-03-01T09:00:00Z",
  items: [
    { kind: "thread", ref: "t1", title: "What does the report say", added_at: "2019-03-02T09:00:00Z" },
    { kind: "file", ref: "doc_gone", title: "", added_at: "2019-03-02T10:00:00Z" },
  ],
  switched_on: true,
};

async function mount(on: boolean, projects: unknown = LISTED(on)) {
  const sent: { path: string; body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        sent.push({ path, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
        return json({});
      }
      if (path === "/api/v1/me/projects") return json(projects);
      if (path === `/api/v1/me/projects/${PROJECT}`) return json(DETAIL);
      if (path === "/api/v1/threads") {
        return json({ items: [{ thread_id: "t2", title: "Another one", last_at: "2019-03-03T09:00:00Z", last_channel: "console" }] });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MyProjects } = await import("../src/components/MyProjects");
  const { container } = render(<MyProjects />);
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name || one.getAttribute("aria-label") === name,
  );
  if (!found) throw new Error(`no button ${name}`);
  return found;
}

describe("the pure rules", () => {
  test("a name is tidied and an empty or over-long one is not sent", () => {
    // What breaks if this is deleted: a project made with a name of only spaces, or with runs of
    // spaces the API would store as typed, or one longer than the column holds.
    expect(nameBody("  Q3   plan ")).toEqual({ name: "Q3 plan" });
    expect(nameBody("   ")).toBeNull();
    expect(nameBody("x".repeat(121))).toBeNull();
    expect(nameBody("x".repeat(120))).not.toBeNull();
  });

  test("a question names a project only when one is chosen", () => {
    // What breaks if this is deleted: every question carries a project field, or a chosen project
    // is dropped before the route reads it.
    expect(projectField("")).toEqual({});
    expect(projectField(PROJECT)).toEqual({ project: PROJECT });
    expect(askBody("what", "", "", "", PROJECT)).toEqual({ question: "what", project: PROJECT });
    expect(askBody("what")).toEqual({ question: "what" });
  });
});

describe("my projects", () => {
  test("a project is made with a tidied name and an empty box makes nothing", async () => {
    // What breaks if this is deleted: a project made with a name the API refuses, or one made from
    // an empty box.
    const { container, sent } = await mount(true, { projects: [], switched_on: true });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_IN_PROJECTS);
    });
    expect(container.textContent).toContain(PROJECTS_NOTE);
    expect(buttonNamed(container, MAKE_LABEL).disabled).toBe(true);
    fireEvent.change(container.querySelector("input") as HTMLInputElement, { target: { value: "  New   plan " } });
    fireEvent.click(buttonNamed(container, MAKE_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([{ path: "/api/v1/me/projects", body: { name: "New plan" } }]);
    });
  });

  test("with the switch off nothing can be made and the person is told, and the list still shows", async () => {
    // What breaks if this is deleted: a switched-off install offers a form that is refused, or
    // hides what the person already made.
    const { container } = await mount(false);
    await waitFor(() => {
      expect(container.textContent).toContain("Quarter plan");
    });
    expect(container.textContent).toContain(NOT_SWITCHED_ON);
    expect(container.querySelector('form[aria-label="Make a project"]')).toBeNull();
  });

  test("opening a project lists its items as they are, with nothing marked unreadable, and taking one out sends its kind and id", async () => {
    // What breaks if this is deleted: a file the person can no longer read is drawn with a mark that
    // tells them so, or taking out sends the wrong item.
    const { container, sent } = await mount(true);
    await waitFor(() => {
      expect(container.textContent).toContain("Quarter plan");
    });
    fireEvent.click(buttonNamed(container, "Open: Quarter plan"));
    await waitFor(() => {
      expect(container.textContent).toContain("Conversation: What does the report say.");
    });
    expect(container.textContent).toContain("File: doc_gone.");
    expect(container.textContent).not.toMatch(/unavailable|no longer|cannot be read|missing/i);
    fireEvent.click(buttonNamed(container, `${TAKE_OUT_LABEL}: file doc_gone`));
    await waitFor(() => {
      expect(sent).toEqual([
        { path: `/api/v1/me/projects/${PROJECT}/items/remove`, body: { kind: "file", ref: "doc_gone" } },
      ]);
    });
  });

  test("putting a project away asks first, says what it does, and sends nothing until confirmed", async () => {
    // What breaks if this is deleted: a project put away with one click, or a confirmation that does
    // not say its documents stay where they are.
    const { container, sent } = await mount(true);
    await waitFor(() => {
      expect(container.textContent).toContain("Quarter plan");
    });
    fireEvent.click(buttonNamed(container, `${PUT_AWAY_LABEL}: Quarter plan`));
    expect(container.textContent).toContain(PUT_AWAY_CONSEQUENCE);
    expect(sent).toEqual([]);
    fireEvent.click(buttonNamed(container, PUT_AWAY_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1/me/projects/${PROJECT}/archive`, body: {} }]);
    });
  });

  test("a conversation is added by its id from the person's own list", async () => {
    // What breaks if this is deleted: a conversation added by title, or a button live with nothing
    // chosen.
    const { container, sent } = await mount(true);
    await waitFor(() => {
      expect(container.textContent).toContain("Quarter plan");
    });
    fireEvent.click(buttonNamed(container, "Open: Quarter plan"));
    await waitFor(() => {
      expect(container.querySelector(`#thread-${PROJECT}`)).not.toBeNull();
    });
    await waitFor(() => {
      expect(container.querySelector(`#thread-${PROJECT} option[value="t2"]`)).not.toBeNull();
    });
    const add = container.querySelector('form[aria-label="Add a conversation"] button') as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    fireEvent.change(container.querySelector(`#thread-${PROJECT}`) as HTMLSelectElement, { target: { value: "t2" } });
    fireEvent.click(add);
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1/me/projects/${PROJECT}/items`, body: { kind: "thread", ref: "t2" } }]);
    });
  });
});

describe("asking inside a project", () => {
  async function mountAsk(projects: unknown) {
    const idp = fakeIdentityProvider({
      api(url) {
        return new URL(url, ORIGIN).pathname === "/api/v1/me/projects" ? json(projects) : null;
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { AskProject } = await import("../src/pages/AskProject");
    const chosen: string[] = [];
    const { container } = render(<AskProject project="" disabled={false} onChange={(one) => chosen.push(one)} />);
    return { container, chosen };
  }

  test("a person with no project is offered no control, and one with projects chooses by id", async () => {
    // What breaks if this is deleted: a dead select for a person with no project, or a choice that
    // sends a name where the route reads an id.
    const none = await mountAsk({ projects: [], switched_on: true });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(none.container.querySelector("select")).toBeNull();
    const some = await mountAsk(LISTED(true));
    await waitFor(() => {
      expect(some.container.querySelector("select")).not.toBeNull();
    });
    expect(some.container.textContent).toContain(PROJECT_LABEL);
    expect(some.container.textContent).toContain(NO_PROJECT);
    expect(some.container.textContent).toContain(PROJECT_NOTE);
    fireEvent.change(some.container.querySelector("select") as HTMLSelectElement, { target: { value: PROJECT } });
    expect(some.chosen).toEqual([PROJECT]);
  });
});
