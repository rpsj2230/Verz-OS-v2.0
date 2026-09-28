/**
 * The Sign-in links page on the page kit: the list, the unlink and its refusal, and the link drawer.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/audit-page.test.tsx` gives. The failures worth testing look like the page working: an
 * unlink control on the last administrator's row, a refusal paraphrased, an identifier drawn where
 * a name belongs, a form that says what it takes only after a refusal, an account ID repeated back
 * after it was sent, and a link sent with space around the account ID.
 *
 * Task ids: M27.7.11, M27.8.5, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  ACCOUNT_LABEL,
  CONFIRM_UNLINK_LABEL,
  KEEP_LABEL,
  LAST_ADMINISTRATOR,
  LINK_A_SIGN_IN,
  LINK_BUTTON,
  LOADING_LINKS,
  NO_LINKS,
  PERSON_LABEL,
  UNLINK_LABEL,
  YOUR_OWN_LINK,
} from "../src/pages/sessions/SignInLinksPage";
import {
  ACCOUNT_HAS_SPACE_AROUND_IT,
  ACCOUNT_HINT,
  ACCOUNT_IS_EMPTY,
  LINK_OUTCOMES,
  PERSON_HINT,
  PERSON_IS_EMPTY,
  linkProblems,
  readLinksPage,
  type LinkRow,
} from "../src/pages/signInLinksQuery";
import { THAT_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED } from "../src/ui/FailureNotice";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredParameterSchema, declaredQueryParameters, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const LINKS_OPERATION = "/api/v1/govern/sign-ins";
const UNLINK_OPERATION = "/api/v1/govern/sign-ins/unlink";
const LINK_OPERATION = "/api/v1/sign-ins";
const CONSOLE_ORIGIN = "https://console.test";
const ACCOUNT_SENTENCE = "ACCOUNT-SENTENCE-SENTINEL";
const UNLINKING = "UNLINKING-SENTENCE-SENTINEL";
const LAST = "LAST-ADMINISTRATOR-SENTINEL";
const ACCOUNT_ID = "9a8b7c6d-0000-4000-8000-0000000000aa";

beforeAll(async () => {
  installRadixStubs();
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

function page(items: LinkRow[], truncated = false): unknown {
  return { items, next_cursor: null, truncated, account: ACCOUNT_SENTENCE, unlinking: UNLINKING, last_administrator: LAST };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
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
    if (!container.querySelector("h1") || container.textContent?.includes(LOADING_LINKS)) {
      throw new Error("still loading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp, operation: string): unknown[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === operation)
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as unknown);
}

async function press(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

async function openDrawer(): Promise<HTMLElement> {
  await press(screen.getByRole("button", { name: LINK_A_SIGN_IN }));
  return screen.findByRole("dialog");
}

describe("what the links page asks for", () => {
  test("the listing and both writes send only what their routes declare", async () => {
    // What breaks if this is deleted: a parameter the API ignores, a page size it refuses, or a body
    // key a route forbids, which is a 422 in front of an administrator who filled the form in.
    const declared = new Set(declaredQueryParameters(LINKS_OPERATION, "get"));
    const limit = declaredParameterSchema(LINKS_OPERATION, "get", "limit");
    const { idp } = await mount((url) => (url.pathname === LINKS_OPERATION ? json(page([])) : null));

    const sent = idp.urls
      .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === LINKS_OPERATION)
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(Object.keys(declaredRequestBodySchema(UNLINK_OPERATION, "post")["properties"] as object)).toEqual(["principal_id"]);
    expect(Object.keys(declaredRequestBodySchema(LINK_OPERATION, "post")["properties"] as object).sort()).toEqual([
      "principal_id",
      "subject",
    ]);
  });

  test("every outcome a link can come back with has a sentence", () => {
    // What breaks if this is deleted: a new refusal code reaches an administrator as nothing at all.
    const schemas = (apiDocument()["components"] as Record<string, unknown>)["schemas"] as Record<string, Record<string, unknown>>;
    const outcomes = schemas["SignInOutcome"]?.["enum"] as string[];
    expect(outcomes.length).toBeGreaterThan(0);
    expect(Object.keys(LINK_OUTCOMES).sort()).toEqual([...outcomes].sort());
  });
});

describe("what the links page shows and does", () => {
  test("a row names the person and the date, never an id, and the last administrator's row has no unlink", async () => {
    // What breaks if this is deleted: principal ids back beside every name, or a button the store
    // refuses on every press, with no sentence saying why it is missing.
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

    const table = container.querySelector("table")?.textContent ?? "";
    expect(table).toContain("Wei Ling Tan");
    expect(table).toContain(LAST_ADMINISTRATOR);
    expect(container.textContent).not.toContain("u_one");
    expect(container.textContent).not.toContain("u_admin");
    expect(container.textContent).toContain(LAST);
    const unlinks = [...container.querySelectorAll("tbody button")]
      .map((one) => one.getAttribute("aria-label"))
      .filter((one) => one?.startsWith(UNLINK_LABEL));
    expect(unlinks).toEqual([`${UNLINK_LABEL}: Wei Ling Tan`]);
  });

  test("unlinking is confirmed, warns you about your own, sends one key and asks for the list again", async () => {
    // What breaks if this is deleted: a press that unlinks with no second step, an administrator
    // unlinking themselves without being told they will be signed out, or a stale list.
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

    await press(screen.getByRole("button", { name: `${UNLINK_LABEL}: Me Myself` }));
    let dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Me Myself");
    expect(dialog.textContent).toContain(UNLINKING);
    expect(dialog.textContent).toContain(YOUR_OWN_LINK);
    await press(within(dialog).getByRole("button", { name: KEEP_LABEL }));
    expect(posts(idp, UNLINK_OPERATION)).toEqual([]);

    await press(screen.getByRole("button", { name: `${UNLINK_LABEL}: Me Myself` }));
    dialog = await screen.findByRole("alertdialog");
    await press(within(dialog).getByRole("button", { name: CONFIRM_UNLINK_LABEL }));
    await waitFor(() => {
      expect(container.textContent).toContain(NO_LINKS);
    });
    expect(posts(idp, UNLINK_OPERATION)).toEqual([{ principal_id: "u_me" }]);
    expect(container.textContent).toContain(UNLINKING);
  });

  test("an unlink refused as the last administrator's draws the 409's sentence and keeps the row", async () => {
    // What breaks if this is deleted: the 409 reads as "That did not work" with nothing to act on.
    const { container } = await mount((url) => {
      if (url.pathname === UNLINK_OPERATION) {
        return json({ principal_id: "u_one", outcome: "last_administrator", sentence: LAST }, 409);
      }
      return url.pathname === LINKS_OPERATION ? json(page([link({ principal_id: "u_one" })])) : null;
    });

    await press(screen.getByRole("button", { name: `${UNLINK_LABEL}: Wei Ling Tan` }));
    const dialog = await screen.findByRole("alertdialog");
    await press(within(dialog).getByRole("button", { name: CONFIRM_UNLINK_LABEL }));
    await waitFor(() => {
      expect(dialog.textContent).toContain(LAST);
    });
    expect(container.querySelector("table")?.textContent).toContain("Wei Ling Tan");
  });

  test("the link form says what each field takes before anything is sent, and a blank or padded one sends nothing", async () => {
    // What breaks if this is deleted: a form that says what it accepts only after a refusal, an
    // empty form that spends a request, or a padded account ID refused with a code to decode.
    const { idp } = await mount((url) => (url.pathname === LINKS_OPERATION ? json(page([])) : null));
    const drawer = await openDrawer();
    expect(drawer.textContent).toContain(ACCOUNT_HINT);
    expect(drawer.textContent).toContain(PERSON_HINT);
    expect(drawer.textContent).toContain(ACCOUNT_SENTENCE);

    await press(within(drawer).getByRole("button", { name: LINK_BUTTON }));
    expect(drawer.textContent).toContain(ACCOUNT_IS_EMPTY);
    expect(drawer.textContent).toContain(PERSON_IS_EMPTY);
    const person = within(drawer).getByLabelText(PERSON_LABEL);
    expect(person.getAttribute("aria-invalid")).toBe("true");

    fireEvent.change(within(drawer).getByLabelText(ACCOUNT_LABEL), { target: { value: ` ${ACCOUNT_ID}` } });
    fireEvent.change(person, { target: { value: "u_one" } });
    await press(within(drawer).getByRole("button", { name: LINK_BUTTON }));
    expect(drawer.textContent).toContain(ACCOUNT_HAS_SPACE_AROUND_IT);
    expect(posts(idp, LINK_OPERATION)).toEqual([]);
    expect(linkProblems(ACCOUNT_ID, "u_one")).toEqual([]);
  });

  test("a link sends the account once, never shows it again, and says what came of it", async () => {
    // What breaks if this is deleted: the account ID kept in the field or repeated in the result,
    // which puts on the screen the value the server refuses to store.
    const { idp } = await mount((url) => {
      if (url.pathname === LINK_OPERATION) {
        return json({ principal_id: "u_one", outcome: "subject_bound_elsewhere" }, 409);
      }
      return url.pathname === LINKS_OPERATION ? json(page([])) : null;
    });
    const drawer = await openDrawer();
    const account = within(drawer).getByLabelText(ACCOUNT_LABEL) as HTMLInputElement;

    fireEvent.change(account, { target: { value: ACCOUNT_ID } });
    fireEvent.change(within(drawer).getByLabelText(PERSON_LABEL), { target: { value: "u_one" } });
    await press(within(drawer).getByRole("button", { name: LINK_BUTTON }));

    await waitFor(() => {
      expect(drawer.textContent).toContain(LINK_OUTCOMES["subject_bound_elsewhere"]);
    });
    expect(posts(idp, LINK_OPERATION)).toEqual([{ subject: ACCOUNT_ID, principal_id: "u_one" }]);
    expect(account.value).toBe("");
    expect(document.body.textContent).not.toContain(ACCOUNT_ID);
  });

  test("a link the API accepts closes the drawer, says so, and asks for the list again", async () => {
    // What breaks if this is deleted: a success that says nothing, or a list that does not show the
    // person who can now sign in.
    let linked = false;
    const { container } = await mount((url) => {
      if (url.pathname === LINK_OPERATION) {
        linked = true;
        return json({ principal_id: "u_one", outcome: "bound" });
      }
      return url.pathname === LINKS_OPERATION ? json(page(linked ? [link({ principal_id: "u_one" })] : [])) : null;
    });
    const drawer = await openDrawer();
    fireEvent.change(within(drawer).getByLabelText(ACCOUNT_LABEL), { target: { value: ACCOUNT_ID } });
    fireEvent.change(within(drawer).getByLabelText(PERSON_LABEL), { target: { value: "u_one" } });
    await press(within(drawer).getByRole("button", { name: LINK_BUTTON }));

    await waitFor(() => {
      expect(container.textContent).toContain(LINK_OUTCOMES["bound"]);
    });
    await waitFor(() => {
      expect(container.querySelector("table")?.textContent).toContain("Wei Ling Tan");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("empty, refused and unreachable are different sentences", async () => {
    // What breaks if this is deleted: "nobody can sign in" said when the Brain could not be reached.
    const empty = await mount((url) => (url.pathname === LINKS_OPERATION ? json(page([])) : null));
    expect(empty.container.textContent).toContain(NO_LINKS);

    const refused = await mount((url) =>
      url.pathname === LINKS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(THAT_DID_NOT_WORK);
    expect(refused.container.textContent).not.toContain(NO_LINKS);

    const unreachable = await mount((url) => {
      if (url.pathname === LINKS_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
  });

  test("a body that is not a page is an empty one, a malformed row is dropped, and no total survives", () => {
    // What breaks if this is deleted: an unreadable answer throws inside a render, or a `total`
    // has a path to a renderer.
    expect(readLinksPage(null).links).toEqual([]);
    const read = readLinksPage({ ...(page([link({ principal_id: "u_one" })]) as object), items: [link({ principal_id: "u_one" }), { principal_id: "u_two" }], total: 3 });
    expect(read.links.map((one) => one.principal_id)).toEqual(["u_one"]);
    expect(Object.keys(read).sort()).toEqual(["account", "lastAdministrator", "links", "truncated", "unlinking"]);
  });
});
