/**
 * The Skills screen: the library, what a skill is trusted to reach, the queue, and the three
 * writes, asserted over the rendered page and over what was sent.
 *
 * **Every control is drawn from a flag the API sent**, so the refusals worth testing are the
 * controls that must not be drawn: an Add form for a reader who may not add, an Approve button on
 * a skill the reader added, an Assign form for a skill nobody approved. Each has a sibling where
 * the flag is true and the control is there, because a page drawing no controls would pass every
 * refusal.
 *
 * **Nothing around the listings may count anything.** The listings are filtered per caller, so a
 * number is the subtraction `CLAUDE.md` forbids. The queue's counts are the exception and they are
 * the API's own.
 *
 * **The route's bounds and the request bodies are read out of the API's own document**, and the
 * one figure copied from Python, the largest package, is read out of the Python source.
 *
 * **The real route table is mounted**, which is `routing.test.tsx`'s rule: the skill name is a
 * path segment, so the route is half of what is under test.
 *
 * Task ids: M42.6.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  A_SKILL_HAS_NO_REACH_OF_ITS_OWN,
  ADD,
  ADD_HEADING,
  APPROVE,
  ASSIGN,
  DRIFT_IS_PINNED_BY_DESIGN,
  NO_DRIFT,
  NO_LIBRARY,
  NO_SKILLS,
  NO_SUCH_SKILL,
  NOT_ON_THIS_INSTALL,
  NOTHING_IS_WAITING,
  PASTE_LABEL,
  REJECT,
  queueCount,
} from "../src/pages/Skills";
import {
  MAX_PACKAGE_BYTES,
  REVIEW_WORDS,
  assignedSentence,
  assignPath,
  base64Of,
  chosen,
  driftingRows,
  packageProblem,
  pasted,
  readSkillsPage,
  reviewPath,
  skillAddress,
  skillIn,
  skillApiPath,
  type SkillLibraryRow,
} from "../src/pages/skillsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  declaredParameterSchema,
  declaredQueryParameters,
  declaredRequestBodySchema,
  declaredPropertyNames,
} from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { extractOne, readRepoFile } from "./support/repo";

const API = "/api/v1";
const SKILLS_OPERATION = `${API}/skills`;
const CONSOLE_ORIGIN = "https://console.test";
const DIGEST_ONE = "a".repeat(64);
const DIGEST_TWO = "b".repeat(64);
const ROUTES = "src/brain/skill_routes.py";

interface QueueRow {
  name: string;
  digest: string;
  waiting_since: string;
  changed: string[];
  stale: boolean;
}

/** One library row in the shape `brain.skill_routes.LibrarySkillView` serialises. */
function librarySkill(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    digest: DIGEST_ONE,
    name: "hosting-expiry",
    version: "1.0.0",
    description: "Checks whether a client domain is close to renewal",
    source: "upload",
    source_location: "SKILL.md",
    submitted_by: "u_importer",
    submitted_at: "2019-03-04T09:00:00Z",
    review: "pending",
    reviewer: null,
    reviewed_at: null,
    tools: [
      { name: "crm.read_client", capability: "read:client.name" },
      { name: "erp.read_invoice", capability: null },
    ],
    capabilities: ["read:client.name"],
    unregistered_tools: ["erp.read_invoice"],
    body: "BODY-OF-THE-SKILL",
    reviewable: false,
    assignable: false,
    ...overrides,
  };
}

/** One page in the shape `brain.skill_routes.SkillsPage` serialises. */
function skillsPage(
  items: { name: string; pinned_by: { agent_id: string; digest: string }[]; versions_differ?: boolean }[],
  extra: {
    queue?: QueueRow[];
    truncated?: boolean;
    library?: Record<string, unknown>[];
    agents?: { agent_id: string; display_name: string }[];
    may_add?: boolean;
  } = {},
): Record<string, unknown> {
  const queue = extra.queue ?? [];
  return {
    items: items.map((one) => ({
      name: one.name,
      pinned_by: one.pinned_by,
      versions_differ: one.versions_differ ?? false,
    })),
    next_cursor: null,
    total: null,
    truncated: extra.truncated ?? false,
    queue: {
      entries: queue,
      waiting: queue.length,
      edits: queue.filter((one) => one.changed.length > 0).length,
      stale: queue.filter((one) => one.stale).length,
    },
    library: extra.library ?? [],
    library_truncated: false,
    agents: extra.agents ?? [],
    may_add: extra.may_add ?? false,
    registry_is_absent: false,
  };
}

type Answer = (body: unknown) => Response;

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Mount the application's own route table at one address, answering `METHOD /api/v1/...`. */
async function consoleAt(
  path: string,
  answers: Record<string, Answer>,
): Promise<{ container: HTMLElement; idp: FakeIdp; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      const method = (init?.method ?? "GET").toUpperCase();
      const answer = answers[`${method} ${parsed.pathname}`];
      if (answer === undefined) {
        return null;
      }
      const body: unknown =
        typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      sent.push({ method, path: parsed.pathname, body });
      return answer(body);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp, sent };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
}

/** A page answering one listing whatever is asked. */
function listing(body: unknown): Record<string, Answer> {
  return { [`GET ${SKILLS_OPERATION}`]: () => json(body) };
}

/** The button whose accessible name starts with `label`, inside the page. */
function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll(".page button")].find((one) =>
    (one.getAttribute("aria-label") ?? one.textContent ?? "").startsWith(label),
  );
  if (found === undefined) {
    throw new Error(`no button named ${label}`);
  }
  return found as HTMLButtonElement;
}

/** The confirmation's button with exactly this text. */
function confirmButton(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll(".confirm button")].find(
    (one) => one.textContent === label,
  );
  if (found === undefined) {
    throw new Error(`no confirmation button ${label}`);
  }
  return found as HTMLButtonElement;
}

/** Every digit the page rendered, so a count outside the queue is a failure. */
function digitsOn(container: HTMLElement): string[] {
  return (container.querySelector(".page")?.textContent ?? "").match(/\d+/g) ?? [];
}

describe("what the skills screen asks for and sends", () => {
  test("the listing sends only a query parameter the route declares", async () => {
    // What breaks if this is deleted: a parameter the API ignores, read as the page it asked for.
    const declared = new Set(declaredQueryParameters(SKILLS_OPERATION, "get"));
    const { idp } = await consoleAt("/skills", listing(skillsPage([])));

    const asked = idp.urls
      .filter((url) => url.includes(SKILLS_OPERATION))
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);

    expect(asked.length).toBeGreaterThan(0);
    expect(asked.filter((name) => !declared.has(name))).toEqual([]);
  });

  test("the page size this console asks for is one the route will answer", () => {
    // What breaks if this is deleted: every load of this screen becomes a 422.
    const limit = declaredParameterSchema(SKILLS_OPERATION, "get", "limit");

    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(LIST_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
    expect(skillApiPath("hosting-expiry")).toBe("/skills?limit=1&filter=name%3Ahosting-expiry");
  });

  test("the bodies this console sends are the ones the three writes declare", () => {
    // What breaks if this is deleted: a renamed field in a request the API refuses with a 422
    // that reaches a person as "Something went wrong" every time they press Add or Assign.
    const add = declaredPropertyNames(declaredRequestBodySchema(SKILLS_OPERATION, "post"));
    const review = declaredPropertyNames(
      declaredRequestBodySchema(`${SKILLS_OPERATION}/{digest}/review`, "post"),
    );
    const assign = declaredPropertyNames(
      declaredRequestBodySchema(`${SKILLS_OPERATION}/{digest}/assignments`, "post"),
    );

    expect(Object.keys(pasted("x")).sort()).toEqual([...add].sort());
    expect(review).toEqual(["decision"]);
    expect(assign).toEqual(["agent_id"]);
    expect(reviewPath(DIGEST_ONE)).toBe(`/skills/${DIGEST_ONE}/review`);
    expect(assignPath(DIGEST_ONE)).toBe(`/skills/${DIGEST_ONE}/assignments`);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field the page goes on reading as empty.
    expect(Object.keys(librarySkill()).sort()).toEqual(
      backendModelFields(ROUTES, "LibrarySkillView").sort(),
    );
    const page = Object.keys(skillsPage([])).filter((key) => !["items", "next_cursor", "total"].includes(key));
    expect(page.sort()).toEqual(backendModelFields(ROUTES, "SkillsPage").sort());
  });

  test("the largest package is the API's figure and every review state has words", () => {
    // What breaks if this is deleted: a package this console lets through that the API refuses,
    // or a review state drawn as its code.
    const python = readRepoFile("src/brain/console/skill_library.py");
    const kibibytes = extractOne(
      python,
      /^MAX_PACKAGE_BYTES: Final = (\d+) \* 1024$/m,
      "the package bound",
    );

    expect(Number(kibibytes) * 1024).toBe(MAX_PACKAGE_BYTES);
    expect(Object.keys(REVIEW_WORDS).sort()).toEqual(
      Object.values(backendEnumMembers("src/brain/console/agent_tabs.py", "Review")).sort(),
    );
  });

  test("an address this screen builds always stays inside the console", () => {
    // What breaks if this is deleted: an open redirect through a skill name the API sent.
    const hostile = ["\\\\evil.example", "//evil.example", "/\\evil.example", "http://evil.example", ".."];

    for (const name of hostile) {
      const address = skillAddress(name);
      expect(address.startsWith("/skills/")).toBe(true);
      expect(address.includes("evil.example") && !address.includes("%")).toBe(false);
    }
  });
});

describe("adding a skill", () => {
  test("is offered only to a reader who may add, and nothing is offered to one who may not", async () => {
    // What breaks if this is deleted: an Add form whose every press is refused, or no form for the
    // administrator the API said may add.
    const offered = await consoleAt("/skills", listing(skillsPage([], { may_add: true })));
    const withheld = await consoleAt("/skills", listing(skillsPage([], { library: [librarySkill()] })));

    expect(offered.container.querySelector(`form[aria-label="${ADD_HEADING}"]`)).not.toBeNull();
    const page = withheld.container.querySelector(".page") as HTMLElement;
    expect(page.querySelectorAll("button")).toHaveLength(0);
    // No form but the search every list draws.
    expect(page.querySelector('form:not([role="search"])')).toBeNull();
  });

  test("a paste is checked before it is sent, sent as text, and the page says so and reads again", async () => {
    // What breaks if this is deleted: an empty or oversized package sent to be refused, a paste
    // sent in a shape the route does not take, or a page that goes on drawing the old library.
    let library: Record<string, unknown>[] = [];
    const { container, sent } = await consoleAt("/skills", {
      [`GET ${SKILLS_OPERATION}`]: () => json(skillsPage([], { may_add: true, library })),
      [`POST ${SKILLS_OPERATION}`]: () => {
        library = [librarySkill()];
        return json(librarySkill(), 201);
      },
    });

    const field = container.querySelector("#skills-paste") as HTMLTextAreaElement;
    expect(container.querySelector("label[for=skills-paste]")?.textContent).toBe(PASTE_LABEL);
    expect(button(container, ADD).disabled).toBe(true);
    fireEvent.change(field, { target: { value: "x".repeat(MAX_PACKAGE_BYTES + 1) } });
    expect(container.textContent).toContain("at most 256 KB");
    expect(button(container, ADD).disabled).toBe(true);

    fireEvent.change(field, { target: { value: "---\nname: hosting-expiry\n---\n" } });
    fireEvent.click(button(container, ADD));

    await waitFor(() => {
      expect(container.textContent).toContain("was added and is waiting for review");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { file_name: "SKILL.md", content: "---\nname: hosting-expiry\n---\n", encoding: "text" },
    ]);
    // Waited for: the library is read again after the sentence is drawn, and under a loaded run
    // the second answer can land a tick after the page has settled on the first.
    await waitFor(() => {
      expect(container.querySelector('[aria-label="Skills in the library"]')?.textContent).toContain(
        "hosting-expiry",
      );
    });
    expect(sent.filter((one) => one.method === "GET").length).toBe(2);
  });

  test("a refusal is said in the API's words and the page is not read again", async () => {
    // What breaks if this is deleted: the reason a package was refused replaced by a generic
    // sentence, a refused write drawn as though it had worked, or the refusal drawn without the
    // reference that finds it in the server's log. It is drawn in the add card, by the one failure
    // notice, rather than as an alert above the page.
    const { container, sent } = await consoleAt("/skills", {
      [`GET ${SKILLS_OPERATION}`]: () => json(skillsPage([], { may_add: true })),
      [`POST ${SKILLS_OPERATION}`]: () =>
        json({ message: "this skill was not added: it declares scripts", trace_id: "t" }, 404),
    });

    fireEvent.change(container.querySelector("#skills-paste") as HTMLTextAreaElement, {
      target: { value: "---\nname: x\n---\n" },
    });
    fireEvent.click(button(container, ADD));

    const card = container.querySelector('[aria-labelledby="skills-add"]') as HTMLElement;
    await waitFor(() => {
      expect(card.querySelector(".notice__body > p")?.textContent).toBe(
        "this skill was not added: it declares scripts",
      );
    });
    expect(card.querySelector(".notice__trace code")?.textContent).toBe("t");
    expect(container.textContent).not.toContain("was added and is waiting for review");
    expect(sent.filter((one) => one.method === "GET").length).toBe(1);
  });

  test("a chosen zip is sent as base64 under its own name and a SKILL.md as text", () => {
    // What breaks if this is deleted: an archive's bytes mangled by being read as text, which the
    // API cannot open, or a SKILL.md sent as base64 the parser reads as nonsense.
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0xff]);

    expect(chosen("hosting.zip", bytes)).toEqual({
      file_name: "hosting.zip",
      content: base64Of(bytes),
      encoding: "base64",
    });
    expect(chosen("SKILL.md", new TextEncoder().encode("---\n"))).toEqual({
      file_name: "SKILL.md",
      content: "---\n",
      encoding: "text",
    });
    expect(packageProblem(null)).not.toBeNull();
    expect(packageProblem(pasted("---"))).toBeNull();
  });
});

describe("what a skill is trusted to reach, and deciding about it", () => {
  test("an open skill lists each tool with what it requires and a tool this install lacks as such", async () => {
    // What breaks if this is deleted: the reach SCREEN 6 asks for is not on the screen, or a tool
    // nothing registers is drawn as a tool requiring nothing.
    const { container } = await consoleAt(
      skillAddress("hosting-expiry"),
      listing(skillsPage([], { library: [librarySkill()] })),
    );

    const reach = container.querySelector('[aria-label="Tools this skill names"]')?.textContent ?? "";
    expect(reach).toContain("crm.read_client");
    expect(reach).toContain("read:client.name");
    expect(reach).toContain(`erp.read_invoice ${NOT_ON_THIS_INSTALL}`);
    expect(container.textContent).toContain(A_SKILL_HAS_NO_REACH_OF_ITS_OWN);
    expect(container.textContent).toContain(REVIEW_WORDS["pending"]);
  });

  test("the instructions are drawn only when the API sent them", async () => {
    // What breaks if this is deleted: the page drawing a body the API withheld, from somewhere else.
    const sent = await consoleAt(skillAddress("hosting-expiry"), listing(skillsPage([], { library: [librarySkill()] })));
    const withheld = await consoleAt(
      skillAddress("hosting-expiry"),
      listing(skillsPage([], { library: [librarySkill({ body: null })] })),
    );

    expect(sent.container.textContent).toContain("BODY-OF-THE-SKILL");
    expect(withheld.container.querySelector("details")).toBeNull();
  });

  test("approve is offered only where the API says the reader may decide, is confirmed, posted and read again", async () => {
    // What breaks if this is deleted: an Approve button on a skill its reader added, which is
    // refused every time, or an approval sent without the confirmation saying what it does.
    let review = "pending";
    const refused = await consoleAt(
      skillAddress("hosting-expiry"),
      listing(skillsPage([], { library: [librarySkill()] })),
    );
    const { container, sent } = await consoleAt(skillAddress("hosting-expiry"), {
      [`GET ${SKILLS_OPERATION}`]: () =>
        json(skillsPage([], { library: [librarySkill({ review, reviewable: review === "pending" })] })),
      [`POST ${SKILLS_OPERATION}/${DIGEST_ONE}/review`]: () => {
        review = "approved";
        return json(librarySkill({ review, reviewer: "u_reviewer", reviewed_at: "2019-03-05T09:00:00Z" }));
      },
    });

    expect(() => button(refused.container, APPROVE)).toThrow();
    expect(button(container, REJECT)).toBeDefined();
    fireEvent.click(button(container, APPROVE));
    expect(container.querySelector(".confirm")?.textContent).toContain("added by u_importer");
    fireEvent.click(confirmButton(container, APPROVE));

    await waitFor(() => {
      expect(container.textContent).toContain("hosting-expiry 1.0.0 is approved.");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { decision: "approve" },
    ]);
    // Waited for rather than asserted at once: the page reads the skill again after the POST,
    // and until that answer is drawn the button from the pending state is still on screen. On a
    // loaded CI runner that gap was long enough to fail this line (ece82dc), with nothing wrong.
    // The paste test above waits for the same kind of re-read.
    await waitFor(() => {
      expect(() => button(container, APPROVE)).toThrow();
    });
  });
});

describe("assigning a skill", () => {
  test("is offered only for an approved skill, with the agents the API listed, confirmed with the agent named", async () => {
    // What breaks if this is deleted: an Assign form beside a skill nobody approved, an agent
    // offered that the API did not list, or an assignment sent to an agent the person did not
    // read the name of.
    const agents = [
      { agent_id: "company_desk", display_name: "Company Desk" },
      { agent_id: "web_desk", display_name: "Web Desk" },
    ];
    const pending = await consoleAt(
      skillAddress("hosting-expiry"),
      listing(skillsPage([], { library: [librarySkill({ assignable: false })], agents })),
    );
    const { container, sent } = await consoleAt(skillAddress("hosting-expiry"), {
      [`GET ${SKILLS_OPERATION}`]: () =>
        json(
          skillsPage([], {
            library: [librarySkill({ review: "approved", reviewer: "u_reviewer", assignable: true })],
            agents,
          }),
        ),
      [`POST ${SKILLS_OPERATION}/${DIGEST_ONE}/assignments`]: () =>
        json(
          {
            agent_id: "web_desk",
            skill_name: "hosting-expiry",
            digest: DIGEST_ONE,
            replaced_digest: null,
            reach: ["crm.read_client"],
            effective_hash: DIGEST_TWO,
          },
          201,
        ),
    });

    expect(() => button(pending.container, ASSIGN)).toThrow();
    // The assign choice, and not the list's own filters.
    const choices = [...container.querySelectorAll("select")].filter((one) => one.closest('form[role="search"]') === null);
    const options = choices.flatMap((one) => [...one.querySelectorAll("option")]).map((one) => one.textContent);
    expect(options).toEqual(["Company Desk", "Web Desk"]);
    fireEvent.change(choices[0] as HTMLSelectElement, {
      target: { value: "web_desk" },
    });
    fireEvent.click(button(container, ASSIGN));
    expect(container.querySelector(".confirm")?.textContent).toContain("Assign hosting-expiry 1.0.0 to Web Desk?");
    fireEvent.click(confirmButton(container, ASSIGN));

    await waitFor(() => {
      expect(container.textContent).toContain(
        "hosting-expiry was assigned to Web Desk. Through that agent it can use, for you: crm.read_client.",
      );
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { agent_id: "web_desk" },
    ]);
  });

  test("an assignment that reaches nothing says so rather than listing nothing", () => {
    // What breaks if this is deleted: an empty reach drawn as a sentence ending in a colon, which
    // reads as a list that failed to load.
    expect(
      assignedSentence(
        {
          agent_id: "web_desk",
          skill_name: "hosting-expiry",
          digest: DIGEST_ONE,
          replaced_digest: null,
          reach: [],
          effective_hash: DIGEST_TWO,
        },
        undefined,
      ),
    ).toContain("none of the tools it names");
  });
});

describe("what the skills screen shows beside the library", () => {
  test("a skill in use is drawn with every agent pinned to it and the bytes each one runs", async () => {
    // What breaks if this is deleted: every refusal here is satisfied by a page that renders nothing.
    const { container } = await consoleAt(
      "/skills",
      listing(
        skillsPage([
          {
            name: "hosting-expiry",
            pinned_by: [
              { agent_id: "company-desk", digest: DIGEST_ONE },
              { agent_id: "web-helper", digest: DIGEST_ONE },
            ],
          },
        ]),
      ),
    );

    const inUse = container.querySelector('[aria-label="Skills in use"]')?.textContent ?? "";
    expect(inUse).toContain("hosting-expiry");
    expect(inUse).toContain("company-desk");
    expect(inUse).toContain("web-helper");
    expect(inUse).toContain(DIGEST_ONE);
  });

  test("an empty library and nothing in use each say one sentence", async () => {
    // What breaks if this is deleted: two sentences for "this company has none" and "you may see
    // none", whose difference is a fact about what this reader was not shown.
    const { container } = await consoleAt("/skills", listing(skillsPage([])));

    expect(container.textContent).toContain(NO_LIBRARY);
    expect(container.textContent).toContain(NO_SKILLS);
    expect(container.textContent).toContain(NOTHING_IS_WAITING);
  });

  test("nothing outside the review queue is a number", async () => {
    // What breaks if this is deleted: a heading saying how many skills there are, which on a
    // listing filtered per caller tells a reader how many they were not shown.
    const { container } = await consoleAt(
      "/skills",
      listing(
        skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }], {
          truncated: true,
        }),
      ),
    );

    expect(digitsOn(container)).toEqual([]);
  });

  test("a queue entry is listed with the counts computed over exactly those entries", async () => {
    // What breaks if this is deleted: the counts and the list stop being one answer.
    const { container } = await consoleAt(
      "/skills",
      listing(
        skillsPage([], {
          queue: [
            {
              name: "xero-reconciliation",
              digest: DIGEST_TWO,
              waiting_since: "2019-03-04T09:00:00Z",
              changed: ["body"],
              stale: true,
            },
          ],
        }),
      ),
    );

    expect(container.textContent).toContain("xero-reconciliation");
    expect(container.textContent).toContain(queueCount(1, 1, 1));
    expect(container.textContent).not.toContain(NOTHING_IS_WAITING);
  });

  test("two agents on different bytes of one skill are listed as drift, and matching ones are not", async () => {
    // What breaks if this is deleted: the drift card goes quiet.
    const drifting = await consoleAt(
      "/skills",
      listing(
        skillsPage([
          {
            name: "hosting-expiry",
            pinned_by: [
              { agent_id: "a", digest: DIGEST_ONE },
              { agent_id: "b", digest: DIGEST_TWO },
            ],
            versions_differ: true,
          },
        ]),
      ),
    );
    const steady = await consoleAt(
      "/skills",
      listing(skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }])),
    );

    expect(drifting.container.querySelector('[aria-label="Skills whose agents run different bytes"]')).not.toBeNull();
    expect(drifting.container.textContent).toContain(DRIFT_IS_PINNED_BY_DESIGN);
    expect(steady.container.textContent).toContain(NO_DRIFT);
  });

  test("a deep link to a skill this page does not carry says so about the page", async () => {
    // What breaks if this is deleted: the sentence becomes about the company, which is the oracle a
    // deep link resolved against the page exists to avoid.
    const { container } = await consoleAt(
      skillAddress("quote-format"),
      listing(skillsPage([{ name: "hosting-expiry", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }])),
    );

    expect(container.textContent).toContain(NO_SUCH_SKILL);
    expect(container.textContent).not.toMatch(/does not exist|not found|never imported/i);
  });

  test("an open skill draws its own pins and asks the listing once more, for its own name only", async () => {
    // What breaks if this is deleted: the deep link asking something other than its own row, or
    // finding its pins only when the skill happens to sit on the first page of the list.
    const rows = skillsPage([
      { name: "hosting-expiry", pinned_by: [{ agent_id: "company-desk", digest: DIGEST_ONE }] },
    ]);
    const open = await consoleAt(skillAddress("hosting-expiry"), listing(rows));
    const bare = await consoleAt("/skills", listing(rows));

    const asked = (idp: FakeIdp) =>
      idp.urls
        .filter((url) => url.includes(SKILLS_OPERATION))
        .map((url) => new URL(url, CONSOLE_ORIGIN).pathname + new URL(url, CONSOLE_ORIGIN).search);

    expect(asked(open.idp).sort()).toEqual([...asked(bare.idp), `/api/v1${skillApiPath("hosting-expiry")}`].sort());
    expect(open.container.querySelector('section.card[aria-label="hosting-expiry"]')?.textContent).toContain(
      "company-desk",
    );
    expect(bare.container.querySelector('section.card[aria-label="hosting-expiry"]')).toBeNull();
  });
});

describe("what the query module does with a body", () => {
  test("a body that is not a page is an empty page offering nothing", () => {
    // What breaks if this is deleted: an unreadable answer draws an Add form whose every press is
    // refused, because the console understood least exactly where it offered most.
    const page = readSkillsPage({ unexpected: true });

    expect(page.skills).toEqual([]);
    expect(page.library).toEqual([]);
    expect(page.mayAdd).toBe(false);
    expect(page.agents).toEqual([]);
  });

  test("the total and the cursor have no path from the payload to a renderer", () => {
    // What breaks if this is deleted: `total` reaches a component and a footer counts rows.
    const page = readSkillsPage(
      skillsPage([{ name: "a-skill", pinned_by: [{ agent_id: "a", digest: DIGEST_ONE }] }]),
    );

    expect(Object.keys(page).sort()).toEqual(
      [
        "agents",
        "edits",
        "library",
        "libraryTruncated",
        "mayAdd",
        "queue",
        "registryIsAbsent",
        "skills",
        "stale",
        "truncated",
        "waiting",
      ].sort(),
    );
  });

  test("a skill is found on the page by its exact name and never by a prefix", () => {
    // What breaks if this is deleted: `/skills/hosting` opens `hosting-expiry`.
    const rows = [
      { name: "hosting-expiry", pinned_by: [], versions_differ: false },
      { name: "hosting", pinned_by: [], versions_differ: false },
    ] as unknown as SkillLibraryRow[];

    expect(skillIn(rows, "hosting")?.name).toBe("hosting");
    expect(skillIn(rows, "hosting-exp")).toBeNull();
  });

  test("drift is the rows the API marked and never a comparison this console made", () => {
    // What breaks if this is deleted: the console decides drift over rows it may not have all of.
    const rows = [
      { name: "a-skill", pinned_by: [], versions_differ: true },
      { name: "b-skill", pinned_by: [], versions_differ: false },
    ] as unknown as SkillLibraryRow[];

    expect(driftingRows(rows).map((one) => one.name)).toEqual(["a-skill"]);
  });
});
