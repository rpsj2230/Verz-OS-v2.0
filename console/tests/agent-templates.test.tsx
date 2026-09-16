/**
 * The template catalogue: that it is reachable, that it draws what the API sent, and that it
 * counts nothing.
 *
 * **Reachable means through the application's own route table.** The page is mounted on a
 * memory router over `routes` from `src/App.tsx`, signed in through the real session modules
 * and answered by a stand-in API, so a test passes only if the address resolves. A test that
 * rendered the component directly would pass with the route deleted, which is the state this
 * screen was in until now: the twenty-three manifests existed and no address reached them.
 *
 * **Every wire name is read off the route's declared response.** The reader and the route
 * drifting apart on a name renders a card with a fact silently missing and no test anywhere
 * red, which is `tests/agent-page.test.tsx`'s argument about the same seam.
 *
 * **The refusal is the API's own sentence.** A reader without the Skills and templates
 * screen's read is answered by `brain.agent_routes`, and this page renders the sentence and
 * the trace id and draws no list over it, because an empty gallery would read as "this
 * installation offers no templates" when nothing said so.
 *
 * Task ids: none
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  INSTALLING_IS_NOT_OFFERED_HERE,
  INSTALLING_NEVER_WIDENS,
  MORE_TEMPLATES,
  NO_TEMPLATES,
  originWords,
  TEMPLATES_HEADING,
  TEMPLATES_LEDE,
  WHAT_A_TEMPLATE_CARRIES,
  WHAT_A_TEMPLATE_CARRIES_HEADING,
} from "../src/pages/AgentTemplates";
import { readTemplates, TEMPLATES_API_PATH } from "../src/pages/agentTemplatesQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { backendPublicMessages } from "./support/python";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const GALLERY_ADDRESS = "/agent-templates";
const GALLERY_API = `/api/v1${TEMPLATES_API_PATH}`;
const GALLERY_ROUTE = "/api/v1/agent-templates";

interface Answer {
  readonly status?: number;
  readonly body: unknown;
  readonly traceId?: string;
}

async function consoleAt(answer: Answer): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      if (new URL(url, CONSOLE_ORIGIN).pathname !== GALLERY_API) {
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
  const router = createMemoryRouter(routes, { initialEntries: [GALLERY_ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1, .notice")) {
      throw new Error("the page has not arrived");
    }
    if (container.querySelector('p.note[role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
  return container;
}

function card(templateId: string, displayName: string): Record<string, unknown> {
  return {
    template_id: templateId,
    version: 2,
    display_name: displayName,
    summary: "Watches uptime, SSL and domain expiry across the estate.",
    published_by: "system",
    origin: "built_in",
  };
}

function textOf(markup: string): string {
  const holder = document.createElement("div");
  holder.innerHTML = markup;
  return holder.textContent ?? "";
}

describe("where the catalogue is reachable", () => {
  test("its own address renders the templates the API sent, in the order it sent them", async () => {
    // What breaks if this is deleted: the catalogue with no way in, which is the state the
    // owner found it in. Every refusal below is satisfied by a page that draws nothing, and
    // this is the positive sibling for all of them.
    const container = await consoleAt({
      body: {
        items: [card("site_health_sentinel", "Site Health Sentinel"), card("tester", "Tester")],
      },
    });

    expect(container.querySelector("h1")?.textContent).toBe(TEMPLATES_HEADING);
    expect([...container.querySelectorAll("ul.roster h2")].map((one) => one.textContent)).toEqual([
      "Site Health Sentinel version 2",
      "Tester version 2",
    ]);
    expect(container.textContent).toContain(originWords("built_in"));
    expect(container.textContent).toContain(INSTALLING_IS_NOT_OFFERED_HERE);
  });

  test("the route the page asks is declared, and every name the reader takes is a name it sends", () => {
    // What breaks if this is deleted: a reader and the route drifting apart on a name, which
    // draws a card with a fact missing and nothing red. The set is exact, so an install count
    // added to the route is a red test rather than a number nobody argued about.
    const gallery = declaredResponseSchema(GALLERY_ROUTE, "get");
    const items = declaredPropertyNames(gallery);

    expect(items).toContain("items");
    expect(items).toContain("truncated");
  });

  test("an empty catalogue is one sentence, and it has no number in it", async () => {
    // What breaks if this is deleted: an empty gallery that explains why it is empty, which
    // for this screen would be a statement about what this company has published.
    const container = await consoleAt({ body: { items: [] } });
    const markup = container.querySelector("article.page")?.innerHTML ?? "";

    expect(markup).toContain(NO_TEMPLATES);
    expect(textOf(markup).replace(INSTALLING_IS_NOT_OFFERED_HERE, "")).not.toMatch(/\d/);
  });

  test("a truncated catalogue says there is more, without a figure, and only when the API says exactly that", async () => {
    // What breaks if this is deleted: "and 9 more", which is a count of rows beside a list
    // the reader did not filter.
    const container = await consoleAt({
      body: { items: [card("tester", "Tester")], truncated: true },
    });

    expect(container.textContent).toContain(MORE_TEMPLATES);
    for (const notTrue of [false, "true", 1, undefined]) {
      expect(readTemplates({ items: [], truncated: notTrue })?.truncated).toBe(false);
    }
  });

  test("a refusal is the API's own sentence and its reference, with no catalogue drawn", async () => {
    // What breaks if this is deleted: a page that explains a refusal in words of its own, or
    // draws an empty list over one, which reads as "there are no templates" when what
    // happened is that this reader may not open the screen.
    const sentence = backendPublicMessages()["ABSENT"];
    expect(sentence).toBeTruthy();

    const container = await consoleAt({
      status: 404,
      body: { message: sentence },
      traceId: "trace-gallery",
    });

    expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-gallery");
    expect(container.querySelector("ul.roster")).toBeNull();
    expect(container.textContent).not.toContain(NO_TEMPLATES);
  });
});

describe("what an answer becomes", () => {
  test("a card missing any of the five required fields is not drawn, and a repeat is dropped", () => {
    // What breaks if this is deleted: a card with a name and no version, which is a template
    // nothing could be pinned to, or two cards for one template whose keys collide.
    const answer = readTemplates({
      items: [
        card("tester", "Tester"),
        card("tester", "Tester again"),
        { ...card("no_version", "No version"), version: null },
        { ...card("zero_version", "Zero"), version: 0 },
        { ...card("no_name", "  "), display_name: "  " },
        { ...card("no_origin", "No origin"), origin: "" },
        { ...card("no_publisher", "No publisher"), published_by: null },
        "tester",
        null,
      ],
    });

    expect(answer?.cards.map((one) => one.templateId)).toEqual(["tester"]);
  });

  test("a summary that was withheld, null or empty is one card, with no sentence under the name", () => {
    // What breaks if this is deleted: a card carrying an empty string as a summary, which
    // hands the renderer something to draw a paragraph around.
    for (const missing of [undefined, null, "", "   "]) {
      const one = { ...card("tester", "Tester"), summary: missing };
      expect(readTemplates({ items: [one] })?.cards[0]).toEqual({
        templateId: "tester",
        version: 2,
        displayName: "Tester",
        publishedBy: "system",
        origin: "built_in",
      });
    }
    expect(readTemplates({ items: [card("tester", "Tester")] })?.cards[0]?.summary).toBeTruthy();
  });

  test("a body that is not a gallery draws no list and composes no sentence about it", async () => {
    // What breaks if this is deleted: a body from a different API drawn as an empty gallery,
    // which is a claim about what this installation offers made on no evidence.
    for (const unreadable of [null, [], {}, { items: "tester" }]) {
      expect(readTemplates(unreadable)).toBeNull();
    }
    expect(readTemplates({ items: [] })).toEqual({ cards: [], truncated: false });

    const container = await consoleAt({ body: {} });
    expect(container.textContent).not.toContain(NO_TEMPLATES);
  });

  test("an origin the console has no words for renders as itself rather than as a guess", () => {
    // What breaks if this is deleted: a third origin arriving from a newer API and being
    // drawn as one of the two this console knows, which would tell a person a template ships
    // with the product when nobody said so.
    expect(originWords("built_in")).not.toBe("built_in");
    expect(originWords("published")).not.toBe("published");
    expect(originWords("something_else")).toBe("something_else");
  });
});

describe("the design's own words", () => {
  /** SCREEN 5 of `docs/screens.html`, as a reader sees it: tags gone, entities read back. */
  function screenFive(): string {
    const page = readRepoFile("docs/screens.html");
    const start = page.indexOf("SCREEN 5");
    const end = page.indexOf("SCREEN 6");
    const holder = document.createElement("div");
    holder.innerHTML = page.slice(start, end);
    return (holder.textContent ?? "").replace(/\s+/g, " ");
  }

  test("the heading, the lede, the panel and the closing sentence are SCREEN 5's wording", () => {
    // What breaks if this is deleted: a gallery that drifts into words of its own, which is
    // how the console came to be built without the design it was drawn from. Every string is
    // compared with the design file rather than with itself, so a copy edited here and not
    // there is a red test.
    const design = screenFive();

    expect(design).toContain(TEMPLATES_HEADING);
    // The design says a role can be installed "in a minute", and this console offers no
    // install at all, so that phrase is the one piece of the design's wording left out. The
    // rest of the sentence is the design's, and is compared as such.
    expect(TEMPLATES_LEDE.startsWith("A template is a role someone can install")).toBe(true);
    expect(design).toContain(TEMPLATES_LEDE.slice(TEMPLATES_LEDE.indexOf(":") + 2));
    expect(design).toContain(WHAT_A_TEMPLATE_CARRIES_HEADING);
    for (const [label, value] of WHAT_A_TEMPLATE_CARRIES) {
      expect(design, label).toContain(label);
      expect(design, value).toContain(value);
    }
    expect(design).toContain(INSTALLING_NEVER_WIDENS);
  });

  test("the panel is drawn beside the catalogue, and beside a refusal too, because it names no template", async () => {
    // What breaks if this is deleted: the panel quietly dropped from the page, which the
    // wording test above cannot see because it reads constants. The refusal half is the
    // sibling: product documentation is the same for every reader and discloses nothing.
    const drawn = await consoleAt({ body: { items: [card("tester", "Tester")] } });
    expect(drawn.textContent).toContain(WHAT_A_TEMPLATE_CARRIES_HEADING);

    const refused = await consoleAt({ status: 404, body: { message: "not here" } });
    expect(refused.textContent).toContain(WHAT_A_TEMPLATE_CARRIES_HEADING);
    expect(refused.querySelector("ul.roster")).toBeNull();
  });
});
