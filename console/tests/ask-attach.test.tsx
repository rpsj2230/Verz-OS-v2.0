/**
 * Attaching a file to the conversation on Ask (M12.3.6).
 *
 * **Driven through the application's own route table**, signed in through the real session modules,
 * against a stand-in API answering the upload options, `POST /api/v1/knowledge/uploads` and
 * `POST /api/v1/threads/attachments` with the bodies their routes declare, and `POST /api/v1/answer`
 * with a stream. A file is added at the person's own level and nowhere else, named on the thread,
 * listed by its title, and the next question continues the thread it named.
 *
 * Task ids: M12.3.6
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { EVENT_STREAM } from "../src/api/events";
import { ASK_ADDRESS, ASK_LABEL } from "../src/pages/Ask";
import { ATTACH_LABEL, ATTACHED_LABEL, NOT_A_TYPE_OFFERED } from "../src/pages/AskAttach";
import { ATTACHMENTS_API_PATH } from "../src/pages/askAttachQuery";
import { UPLOAD_OPTIONS_API_PATH, UPLOADS_API_PATH } from "../src/pages/knowledgeQuery";
import { THREAD_HEADER } from "../src/pages/threadsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";
const API = "/api/v1";
const THREAD = "3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b";
const ITEM = "upload.attached.0001";
const TITLE = "Site handover notes";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function options(personal: boolean): unknown {
  return {
    kinds: [
      { value: "sop", label: "Standard operating procedure" },
      { value: "faq", label: "Frequently asked question" },
    ],
    departments: [],
    personal,
    types: [{ media_type: "text/markdown", extensions: [".md"], max_bytes: 100_000 }],
    found_by: "its words",
    checked_by: "",
    offered_as_tables: [],
  };
}

interface Sent {
  readonly path: string;
  readonly search: string;
  readonly body: string;
}

async function askScreen(personal = true): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const address = new URL(url, ORIGIN);
      if (init?.method === "POST") {
        sent.push({
          path: address.pathname,
          search: address.search,
          body: typeof init.body === "string" ? init.body : "",
        });
      }
      if (address.pathname === `${API}${UPLOAD_OPTIONS_API_PATH}`) {
        return json(options(personal));
      }
      if (address.pathname === `${API}${UPLOADS_API_PATH}` && init?.method === "POST") {
        return json(
          { item_id: ITEM, title: TITLE, kind: "sop", level: "personal", department: null, passages: 2, found_by: "its words" },
          201,
        );
      }
      if (address.pathname === `${API}${ATTACHMENTS_API_PATH}` && init?.method === "POST") {
        return json({ thread_id: THREAD, attachment_id: ITEM }, 201);
      }
      if (address.pathname === `${API}/answer`) {
        return new Response("event: text\ndata: It says to sign it.\n\nevent: done\ndata: \n\n", {
          status: 200,
          headers: { "content-type": EVENT_STREAM, [THREAD_HEADER]: THREAD },
        });
      }
      if (address.pathname === `${API}/threads`) {
        return json({ items: [] });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ASK_ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, sent };
}

function attachForm(container: HTMLElement): HTMLFormElement | null {
  return container.querySelector<HTMLFormElement>("form.ask__attach");
}

describe("attaching a file on Ask", () => {
  test("a file is added at the person's own level, named on the thread, listed, and asked about", async () => {
    // What breaks if this is deleted: a file attached at a department's level, where the
    // department reads it, or attached and never named on the thread the next question continues.
    const { container, sent } = await askScreen();
    await waitFor(() => {
      if (attachForm(container) === null) {
        throw new Error("the attach control has not arrived");
      }
    });
    const form = attachForm(container)!;
    const input = form.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["# Site handover\n\nSign it."], "handover.md", { type: "" });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click([...form.querySelectorAll("button")].find((one) => one.textContent === ATTACH_LABEL)!);

    await waitFor(() => {
      if (!container.textContent?.includes(TITLE)) {
        throw new Error("the attached file is not listed");
      }
    });
    const upload = sent.find((one) => one.path === `${API}${UPLOADS_API_PATH}`);
    expect(new URLSearchParams(upload?.search ?? "").get("level")).toBe("personal");
    expect(new URLSearchParams(upload?.search ?? "").get("kind")).toBe("sop");
    const named = sent.find((one) => one.path === `${API}${ATTACHMENTS_API_PATH}`);
    expect(JSON.parse(named?.body ?? "{}")).toEqual({ thread_id: null, attachment_id: ITEM });
    expect(container.querySelector(`section[aria-label="${ATTACHED_LABEL}"]`)?.textContent).toContain(TITLE);

    const question = container.querySelector<HTMLTextAreaElement>("textarea")!;
    fireEvent.change(question, { target: { value: "what does the file I attached say" } });
    fireEvent.click([...container.querySelectorAll("button")].find((one) => one.textContent === ASK_LABEL)!);
    await waitFor(() => {
      if (!sent.some((one) => one.path === `${API}/answer`)) {
        throw new Error("the question was not sent");
      }
    });
    const asked = sent.find((one) => one.path === `${API}/answer`);
    expect((JSON.parse(asked?.body ?? "{}") as { thread?: string }).thread).toBe(THREAD);
  });

  test("a file of a kind the options do not offer is refused before anything is sent", async () => {
    // What breaks if this is deleted: a file the route will refuse is sent anyway, and the
    // person waits for a refusal the page could have given.
    const { container, sent } = await askScreen();
    await waitFor(() => {
      if (attachForm(container) === null) {
        throw new Error("the attach control has not arrived");
      }
    });
    const form = attachForm(container)!;
    const input = form.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["x"], "photo.png", { type: "image/png" })] } });
    fireEvent.click([...form.querySelectorAll("button")].find((one) => one.textContent === ATTACH_LABEL)!);

    await waitFor(() => {
      if (!form.textContent?.includes(NOT_A_TYPE_OFFERED)) {
        throw new Error("the refusal is not shown");
      }
    });
    expect(sent.filter((one) => one.path !== `${API}/threads`)).toEqual([]);
  });

  test("somebody who may not add a document of their own is offered no attach control", async () => {
    // What breaks if this is deleted: a control drawn for a person the route refuses, which fails
    // on every use and reads as a broken page.
    const { container } = await askScreen(false);
    await waitFor(() => {
      if (!container.querySelector("form.ask__form")) {
        throw new Error("the page has not arrived");
      }
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(attachForm(container)).toBeNull();
  });
});
