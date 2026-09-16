/**
 * The Sign-in links screen: the list, the unlink and its refusal, and the link form.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/audit-page.test.tsx` gives. The failures worth testing look like the screen working: an
 * unlink button on the last administrator's row, a refusal paraphrased, an account ID repeated back
 * on the page after it was sent, and a link sent with space around the account ID.
 *
 * Task ids: M27.7.11
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ACCOUNT_LABEL,
  CONFIRM_UNLINK_LABEL,
  KEEP_LABEL,
  KEPT,
  LINK_BUTTON,
  NO_LINKS,
  PERSON_LABEL,
  READING_LINKS,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  UNLINK_LABEL,
  YOUR_OWN_LINK,
} from "../src/pages/SignInLinks";
import {
  ACCOUNT_HAS_SPACE_AROUND_IT,
  ACCOUNT_IS_EMPTY,
  LINK_OUTCOMES,
  LINKS_PAGE_SIZE,
  PERSON_IS_EMPTY,
  linkProblems,
  readLinksPage,
  type LinkRow,
} from "../src/pages/signInLinksQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  apiDocument,
  declaredParameterSchema,
  declaredQueryParameters,
  declaredRequestBodySchema,
} from "./support/openapi";

const LINKS_OPERATION = "/api/v1/govern/sign-ins";
const UNLINK_OPERATION = "/api/v1/govern/sign-ins/unlink";
const LINK_OPERATION = "/api/v1/sign-ins";
const CONSOLE_ORIGIN = "https://console.test";
const ACCOUNT_SENTENCE = "The identity provider account a person signs in with is not stored here.";
const UNLINKING = "Unlinking stops that account signing in as this person from their next request.";
const LAST = "This is the last administrator who can sign in.";
const ACCOUNT_ID = "9a8b7c6d-0000-4000-8000-0000000000aa";

beforeAll(async () => {
  await import("../src/pages/SignInLinks");
}, 60_000);

function link(overrides: Partial<LinkRow> & { principal_id: string }): LinkRow {
  return {
    display_name: "Wei Ling Tan",
    department: "web",
    linked_at: "2019-03-04T09:00:00Z",
    last_administrator: false,
    yours: false,
    ...overrides,
  };
}

function page(items: LinkRow[]): unknown {
  return {
    items,
    truncated: false,
    account: ACCOUNT_SENTENCE,
    unlinking: UNLINKING,
    last_administrator: LAST,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { SignInLinks } = await import("../src/pages/SignInLinks");
  const router = createMemoryRouter([{ path: "/sign-in-links", element: <SignInLinks /> }], {
    initialEntries: ["/sign-in-links"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_LINKS)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp, operation: string): unknown[] {
  return idp.calls
    .filter(
      (call) =>
        call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === operation,
    )
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as unknown);
}

function buttonNamed(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function field(container: HTMLElement, label: string): HTMLInputElement {
  const found = [...container.querySelectorAll("label")].find((one) =>
    one.textContent?.startsWith(label),
  );
  return found?.querySelector("input") as HTMLInputElement;
}

describe("what the links screen asks for", () => {
  test("the listing sends only what the route declares and every write sends what its route declares", async () => {
    // What breaks if this is deleted: a parameter the API ignores, a page size it refuses, or a
    // body key a route forbids, which is a 422 in front of an administrator who filled the form in.
    const declared = new Set(declaredQueryParameters(LINKS_OPERATION, "get"));
    const limit = declaredParameterSchema(LINKS_OPERATION, "get", "limit");
    const { idp } = await mount((url) => (url.pathname === LINKS_OPERATION ? json(page([])) : null));

    const sent = idp.urls
      .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === LINKS_OPERATION)
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LINKS_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(Object.keys(declaredRequestBodySchema(UNLINK_OPERATION, "post")["properties"] as object)).toEqual([
      "principal_id",
    ]);
    expect(
      Object.keys(declaredRequestBodySchema(LINK_OPERATION, "post")["properties"] as object).sort(),
    ).toEqual(["principal_id", "subject"]);
  });

  test("every outcome a link can come back with has a sentence", () => {
    // What breaks if this is deleted: a new refusal code reaches an administrator as nothing at
    // all. The codes are read out of the API's own document.
    const schemas = (apiDocument()["components"] as Record<string, unknown>)["schemas"] as Record<
      string,
      Record<string, unknown>
    >;
    const outcomes = schemas["SignInOutcome"]?.["enum"] as string[];

    expect(outcomes.length).toBeGreaterThan(0);
    expect(Object.keys(LINK_OUTCOMES).sort()).toEqual([...outcomes].sort());
  });
});

describe("what the links screen shows and does", () => {
  test("a link names the person and the date, never an account, and says where the account is", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by an empty page; and the
    // sentence saying the account is kept at the identity provider can be dropped, so a reader
    // hunts for a column that cannot exist.
    const { container } = await mount((url) =>
      url.pathname === LINKS_OPERATION ? json(page([link({ principal_id: "u_one" })])) : null,
    );

    const table = container.querySelector('[aria-label="People who can sign in"]')?.textContent ?? "";
    expect(table).toContain("Wei Ling Tan");
    expect(table).toContain("u_one");
    expect(container.textContent).toContain(ACCOUNT_SENTENCE);
  });

  test("the last administrator's row has no unlink control and says why in the API's words", async () => {
    // What breaks if this is deleted: a button the store will refuse on every press, which reads
    // as the console being broken, with no sentence saying what would have to change.
    const { container } = await mount((url) =>
      url.pathname === LINKS_OPERATION
        ? json(
            page([
              link({ principal_id: "u_admin", display_name: "Only Admin", last_administrator: true }),
              link({ principal_id: "u_one", display_name: "Wei Ling Tan" }),
            ]),
          )
        : null,
    );

    const labels = [...container.querySelectorAll("button")]
      .map((one) => one.getAttribute("aria-label"))
      .filter((one) => one !== null);
    expect(labels).toEqual([`${UNLINK_LABEL}: Wei Ling Tan`]);
    expect(container.textContent).toContain(KEPT);
    expect(container.textContent).toContain(LAST);
  });

  test("unlinking is confirmed, warns you about your own, sends one key and asks for the list again", async () => {
    // What breaks if this is deleted: a press unlinks with no second step, an administrator
    // unlinks themselves without being told they will be signed out, or the list still shows the
    // link that was retired.
    let unlinked = false;
    const { container, idp } = await mount((url) => {
      if (url.pathname === UNLINK_OPERATION) {
        unlinked = true;
        return json({ principal_id: "u_me", outcome: "unlinked", sentence: UNLINKING });
      }
      if (url.pathname === LINKS_OPERATION) {
        return json(page(unlinked ? [] : [link({ principal_id: "u_me", display_name: "Me Myself", yours: true })]));
      }
      return null;
    });

    fireEvent.click(buttonNamed(container, UNLINK_LABEL));
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect(panel.textContent).toContain("Me Myself");
    expect(panel.textContent).toContain(UNLINKING);
    expect(panel.textContent).toContain(YOUR_OWN_LINK);
    fireEvent.click(buttonNamed(container, KEEP_LABEL));
    expect(posts(idp, UNLINK_OPERATION)).toEqual([]);

    fireEvent.click(buttonNamed(container, UNLINK_LABEL));
    fireEvent.click(buttonNamed(container, CONFIRM_UNLINK_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain(NO_LINKS);
    });
    expect(posts(idp, UNLINK_OPERATION)).toEqual([{ principal_id: "u_me" }]);
    expect(container.textContent).toContain(UNLINKING);
  });

  test("an unlink refused as the last administrator's shows the API's sentence and keeps the row", async () => {
    // What breaks if this is deleted: the 409 reads as "That did not work" with nothing an
    // administrator can act on, or as a success.
    const { container } = await mount((url) => {
      if (url.pathname === UNLINK_OPERATION) {
        return json({ principal_id: "u_one", outcome: "last_administrator", sentence: LAST }, 409);
      }
      return url.pathname === LINKS_OPERATION ? json(page([link({ principal_id: "u_one" })])) : null;
    });

    fireEvent.click(buttonNamed(container, UNLINK_LABEL));
    fireEvent.click(buttonNamed(container, CONFIRM_UNLINK_LABEL));

    await waitFor(() => {
      expect(container.textContent).toContain(LAST);
    });
    expect(container.querySelector('[aria-label="People who can sign in"]')?.textContent).toContain(
      "Wei Ling Tan",
    );
  });

  test("a link with a missing or padded account ID is refused before anything is sent", async () => {
    // What breaks if this is deleted: the route refuses a padded ID with a code the administrator
    // has to decode, or an empty form spends a request.
    const { container, idp } = await mount((url) =>
      url.pathname === LINKS_OPERATION ? json(page([])) : null,
    );

    fireEvent.change(field(container, ACCOUNT_LABEL), { target: { value: ` ${ACCOUNT_ID}` } });
    fireEvent.click(buttonNamed(container, LINK_BUTTON));

    expect(container.textContent).toContain(ACCOUNT_HAS_SPACE_AROUND_IT);
    expect(container.textContent).toContain(PERSON_IS_EMPTY);
    expect(posts(idp, LINK_OPERATION)).toEqual([]);
    expect(linkProblems("", "u_one")).toEqual([ACCOUNT_IS_EMPTY]);
    expect(linkProblems(ACCOUNT_ID, "u_one")).toEqual([]);
  });

  test("a link sends the account once, never shows it again, and says what came of it", async () => {
    // What breaks if this is deleted: the account ID stays in the field or is repeated in the
    // result, which puts on the screen the value the server refuses to store.
    const { container, idp } = await mount((url) => {
      if (url.pathname === LINK_OPERATION) {
        return json({ principal_id: "u_one", outcome: "subject_bound_elsewhere" }, 409);
      }
      return url.pathname === LINKS_OPERATION ? json(page([])) : null;
    });

    fireEvent.change(field(container, ACCOUNT_LABEL), { target: { value: ACCOUNT_ID } });
    fireEvent.change(field(container, PERSON_LABEL), { target: { value: "u_one" } });
    fireEvent.click(buttonNamed(container, LINK_BUTTON));

    await waitFor(() => {
      expect(container.textContent).toContain(LINK_OUTCOMES["subject_bound_elsewhere"]);
    });
    expect(posts(idp, LINK_OPERATION)).toEqual([{ subject: ACCOUNT_ID, principal_id: "u_one" }]);
    expect(field(container, ACCOUNT_LABEL).value).toBe("");
    expect(container.textContent).not.toContain(ACCOUNT_ID);
  });

  test("an empty list, unreachable and refused are different sentences", async () => {
    // What breaks if this is deleted: "nobody can sign in" is said when the Brain could not be
    // reached, which is the one sentence that sends an administrator to fix the wrong thing.
    const empty = await mount((url) => (url.pathname === LINKS_OPERATION ? json(page([])) : null));
    expect(empty.container.textContent).toContain(NO_LINKS);

    const refused = await mount((url) =>
      url.pathname === LINKS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).not.toContain(NO_LINKS);

    const unreachable = await mount((url) => {
      if (url.pathname === LINKS_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
  });

  test("a body that is not a page is an empty one with no total on it", () => {
    // What breaks if this is deleted: an unreadable answer throws inside a render, or a `total`
    // has a path to a renderer.
    expect(readLinksPage(null).links).toEqual([]);
    expect(Object.keys(readLinksPage({ ...(page([]) as object), total: 3 })).sort()).toEqual([
      "account",
      "lastAdministrator",
      "links",
      "truncated",
      "unlinking",
    ]);
  });
});
