/**
 * The skills card in My workspace: a person's own skills, adding one, and offering one.
 *
 * Mounted on its own, for the reason `tests/my-workspace-page.test.tsx` gives. The failures worth
 * testing look like the page working: an offer sent without being confirmed, a blank form sent, a
 * skill brought from a repository sent as one written here, and a switch turned off that still
 * offers the form.
 *
 * Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ADD_LABEL, OFFER_LABEL } from "../src/components/MySkills";
import {
  IMPORT_MY_SKILL_API_PATH,
  MY_SKILLS_API_PATH,
  offerMySkillApiPath,
  whatToFill,
  EMPTY_DRAFT,
} from "../src/pages/mySkillsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";
const DIGEST = "a".repeat(64);

beforeAll(async () => {
  await import("../src/components/MySkills");
}, 60_000);

const SKILL = {
  digest: DIGEST,
  name: "hosting-expiry",
  version: "1.0.0",
  origin: "studio",
  location: "SKILL.md",
  review: "pending",
  offered: false,
  offered_at: null,
  made_at: "2019-03-01T09:00:00Z",
  standing: "STANDING-SENTENCE",
  may_offer: true,
};

function answer(overrides: Record<string, unknown> = {}) {
  return { skills: [SKILL], more: false, may_add: true, unavailable: "", ...overrides };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

async function mount(body: unknown = answer(), ready = "hosting-expiry") {
  const sent: { path: string; body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        sent.push({ path, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
        return json(SKILL);
      }
      return path === "/api/v1/me/skills" ? json(body) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MySkills } = await import("../src/components/MySkills");
  const { container } = render(<MySkills />);
  await waitFor(() => {
    expect(container.textContent).toContain(ready);
  });
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name || (one.getAttribute("aria-label") ?? "").startsWith(name),
  );
  if (!found) throw new Error(`no button ${name}`);
  return found;
}

describe("a person's own skills", () => {
  test("each skill is drawn with the sentence the API sent for what it can do now", async () => {
    // What breaks if this is deleted: a card that rewrites the standing in its own words, which
    // could say a skill is ready when the API says nothing runs it.
    const { container } = await mount();
    expect(container.textContent).toContain("STANDING-SENTENCE");
    expect(container.textContent).toContain("written here");
  });

  test("offering is confirmed first, and sends nothing until it is", async () => {
    // What breaks if this is deleted: a one-press offer that cannot be taken back, sent before the
    // person has read what will happen.
    const { container, sent } = await mount();
    fireEvent.click(buttonNamed(container, OFFER_LABEL));
    expect(sent).toEqual([]);
    expect(container.textContent).toContain("cannot take the offer back");
    const confirm = [...container.querySelectorAll(".confirm button")].find(
      (one) => one.textContent === OFFER_LABEL,
    ) as HTMLButtonElement;
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1${offerMySkillApiPath(DIGEST)}`, body: null }]);
    });
  });

  test("a skill already offered has no offer button", async () => {
    // What breaks if this is deleted: a second offer offered, which the API refuses after the person
    // has pressed and confirmed it.
    const { container } = await mount(answer({ skills: [{ ...SKILL, offered: true, may_offer: false }] }));
    expect([...container.querySelectorAll("button")].some((one) => one.textContent === OFFER_LABEL)).toBe(false);
  });

  test("a pasted skill is sent as a text SKILL.md and nothing else", async () => {
    // What breaks if this is deleted: a paste sent with a name or a category the person did not
    // choose, or sent to the import route.
    const { container, sent } = await mount();
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "---\nname: x\n---\nbody" } });
    fireEvent.click(buttonNamed(container, ADD_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([
        {
          path: `/api/v1${MY_SKILLS_API_PATH}`,
          body: { file_name: "SKILL.md", content: "---\nname: x\n---\nbody", encoding: "text" },
        },
      ]);
    });
  });

  test("a skill from a repository is sent to the import route with its commit", async () => {
    // What breaks if this is deleted: a repository skill sent as pasted text, losing the commit
    // that pins it.
    const { container, sent } = await mount();
    fireEvent.change(container.querySelector("select") as HTMLSelectElement, { target: { value: "repository" } });
    const [repository, commit, path] = [...container.querySelectorAll('input[type="text"]')];
    fireEvent.change(repository, { target: { value: "org/skills" } });
    fireEvent.change(commit, { target: { value: "0123456789abcdef0123456789abcdef01234567" } });
    fireEvent.change(path, { target: { value: "skills/one" } });
    fireEvent.click(buttonNamed(container, ADD_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([
        {
          path: `/api/v1${IMPORT_MY_SKILL_API_PATH}`,
          body: {
            kind: "github",
            repository: "org/skills",
            commit: "0123456789abcdef0123456789abcdef01234567",
            path: "skills/one",
            url: "",
          },
        },
      ]);
    });
  });

  test("a blank form says what to fill in, beside its field, and sends nothing", async () => {
    // What breaks if this is deleted: an empty paste sent for the API to refuse, or a refusal not
    // associated with the field it is about.
    const { container, sent } = await mount();
    fireEvent.click(buttonNamed(container, ADD_LABEL));
    expect(sent).toEqual([]);
    const field = container.querySelector("textarea") as HTMLTextAreaElement;
    const said = container.querySelector('[role="alert"]') as HTMLElement;
    expect(said.textContent).toBe(whatToFill(EMPTY_DRAFT));
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toBe(said.id);
  });

  test("a blank address says what to fill in, tied to the field the same way", async () => {
    // What breaks if this is deleted: the association holds for the written skill and not for the
    // other two ways in, so a person using a screen reader is told nothing about the field.
    const { container, sent } = await mount();
    fireEvent.change(container.querySelector("select") as HTMLSelectElement, { target: { value: "address" } });
    fireEvent.click(buttonNamed(container, ADD_LABEL));
    expect(sent).toEqual([]);
    const field = container.querySelector('input[type="text"]') as HTMLInputElement;
    const said = container.querySelector('[role="alert"]') as HTMLElement;
    expect(said.textContent).toBe(whatToFill({ ...EMPTY_DRAFT, way: "address" }));
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toBe(said.id);
  });

  test("with the switch off the form is replaced by the sentence the API sent", async () => {
    // What breaks if this is deleted: a form offered that can only be refused, or a card that
    // hides the skills the person already has.
    const { container } = await mount(answer({ may_add: false, unavailable: "SWITCHED-OFF-SENTENCE" }));
    expect(container.querySelector("form")).toBeNull();
    expect(container.textContent).toContain("SWITCHED-OFF-SENTENCE");
    expect(container.textContent).toContain("hosting-expiry");
  });

  test("an empty list says what adds a row and who", async () => {
    // What breaks if this is deleted: an empty card that says nothing about how to fill it.
    const { container } = await mount(answer({ skills: [] }), "You have not added a skill of your own.");
    expect(container.textContent).toContain("A Member adds one.");
  });
});

describe("what a blank draft is told", () => {
  test("each way names its own missing field and a complete draft is told nothing", () => {
    // What breaks if this is deleted: one sentence for every way, or a complete draft refused.
    expect(whatToFill({ ...EMPTY_DRAFT, way: "address" })).toContain("https address");
    expect(whatToFill({ ...EMPTY_DRAFT, way: "repository", repository: "a/b" })).toContain("commit");
    expect(whatToFill({ ...EMPTY_DRAFT, way: "write", text: "x" })).toBe("");
    expect(whatToFill({ ...EMPTY_DRAFT, way: "address", url: "https://x.test/a" })).toBe("");
    expect(whatToFill({ ...EMPTY_DRAFT, way: "repository", repository: "a/b", commit: "c" })).toBe("");
  });
});
