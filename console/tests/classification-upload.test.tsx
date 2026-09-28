/**
 * The classification screen's two writes: uploading a price list, and marking a column of it.
 *
 * Three properties, each a way this half of the screen could be wrong while looking right.
 *
 * **What is sent is what the route declares.** The upload is a PUT to the table's own address
 * carrying the file as base64, and a mark carries `access` and `derived_from` and nothing that
 * could name a capability. Both bodies are compared with the route's own request schema.
 *
 * **A mark is reviewed before it is applied, and the apply sends exactly what was reviewed.**
 * The Apply control does not exist until a review has come back, and its body is the reviewed
 * mark rather than whatever the form holds by then.
 *
 * **An applied mark says so, and the epoch it moved is shown.** "The policy epoch moves when a
 * derivation changes" is a claim a person checks on this screen, so both digests reach it.
 *
 * Task ids: M7.5.3, M7.7.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  IT_WAS_APPLIED,
  IT_WAS_NOT_UPLOADED,
  REVIEW_BEFORE_APPLYING,
  UPLOAD_HEADING,
  UPLOAD_LEDE,
  WHAT_THE_EPOCH_IS,
} from "../src/pages/Classification";
import {
  base64Of,
  columnMarkSchema,
  MARK_WORDS,
  readUploaded,
  submittedMark,
  uploadBody,
  type ColumnRow,
} from "../src/pages/classificationQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredRequestBodySchema } from "./support/openapi";

const ENTITY = "prices";
const TABLE_OPERATION = "/api/v1/classifications/{entity}/table";
const MARK_OPERATION = "/api/v1/classifications/{entity}/columns/{column}/marks";

beforeAll(async () => {
  await import("../src/pages/Classification");
}, 60_000);

function row(overrides: Partial<ColumnRow>): ColumnRow {
  return {
    column: "margin",
    required_capability: "read:prices.margin",
    classification: "confidential",
    derived_from: ["cost", "sell_price"],
    access: "derived",
    ...overrides,
  };
}

function stored(epoch: string): unknown {
  return {
    entity: ENTITY,
    columns: [
      row({ column: "cost", required_capability: "read:prices.cost", derived_from: ["margin", "sell_price"] }),
      row({}),
      row({
        column: "sell_price",
        required_capability: "read:prices",
        classification: "internal",
        derived_from: [],
        access: "open",
      }),
    ],
    epoch,
    editable: true,
    stored: true,
    title: "Price list",
    key_column: "name",
  };
}

function reviewedMark(extra: Record<string, unknown> = {}): unknown {
  return {
    entity: ENTITY,
    column: "margin",
    would_not_load: "",
    changes: ["derivation_dropped"],
    widens: true,
    exposed: ["cost"],
    epoch_now: "EPOCH-BEFORE-0000",
    epoch_after: "EPOCH-AFTER-11111",
    ...extra,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Every call this console made about classifications, with its method and parsed body. */
function sent(idp: FakeIdp): { method: string; url: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.url.includes("/api/v1/classifications"))
    .map((call) => ({
      method: call.init?.method ?? "GET",
      url: call.url,
      body: call.init?.body === undefined ? null : JSON.parse(String(call.init.body)),
    }));
}

async function mount(
  path: string,
  api: (url: string, method: string) => Response | null,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return url.includes("/api/v1/classifications") ? api(url, init?.method ?? "GET") : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  return { container, idp };
}

function type(container: HTMLElement, id: string, value: string): void {
  const input = container.querySelector(`#${id}`) as HTMLInputElement;
  fireEvent.change(input, { target: { value } });
}

describe("uploading a price list", () => {
  test("the file goes to the table's own address as base64 and the table opens", async () => {
    // What breaks if this is deleted: the upload can send the file somewhere else, in another
    // encoding, or leave a person on the form after the table was stored.
    let reads = 0;
    const { container, idp } = await mount("/classification", (url, method) => {
      if (method === "PUT" && url.endsWith(`/classifications/${ENTITY}/table`)) {
        return json({ refused: "", classification: stored("EPOCH-A") });
      }
      if (method === "GET") {
        reads += 1;
        return json(stored("EPOCH-A"));
      }
      return null;
    });
    await waitFor(() => expect(container.textContent).toContain(UPLOAD_HEADING));

    type(container, "classification-entity", ENTITY);
    type(container, "classification-title", "Price list");
    type(container, "classification-key", "Name");
    const file = new File(["Name,Sell Price\nHosting,300\n"], "prices.csv", { type: "text/csv" });
    fireEvent.change(container.querySelector("#classification-file") as HTMLInputElement, {
      target: { files: [file] },
    });
    const upload = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === "Upload",
    ) as HTMLButtonElement;
    await waitFor(() => expect(upload.disabled).toBe(false));
    await act(async () => {
      fireEvent.click(upload);
    });

    await waitFor(() => expect(reads).toBeGreaterThan(0));
    const put = sent(idp).find((one) => one.method === "PUT");
    expect(put?.url).toContain(`/api/v1/classifications/${ENTITY}/table`);
    const body = put?.body as Record<string, unknown>;
    expect(atob(String(body["content_base64"]))).toBe("Name,Sell Price\nHosting,300\n");
    expect(body["filename"]).toBe("prices.csv");
    expect(body["key_column"]).toBe("Name");
    const declared = declaredRequestBodySchema(TABLE_OPERATION, "put");
    expect(Object.keys(body).sort()).toEqual(Object.keys(declared.properties ?? {}).sort());
  });

  test("a refused upload shows the API's sentence and opens nothing", async () => {
    // What breaks if this is deleted: a refusal the uploader could act on ("two headings both
    // become the column 'name'") is swallowed, or the screen moves to a table that was never
    // stored.
    const { container, idp } = await mount("/classification", (_url, method) =>
      method === "PUT"
        ? json({ refused: "REFUSAL-SENTINEL", classification: null })
        : null,
    );
    await waitFor(() => expect(container.textContent).toContain(UPLOAD_HEADING));
    type(container, "classification-entity", ENTITY);
    type(container, "classification-title", "Price list");
    fireEvent.change(container.querySelector("#classification-file") as HTMLInputElement, {
      target: { files: [new File(["a"], "prices.csv")] },
    });
    const upload = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === "Upload",
    ) as HTMLButtonElement;
    await waitFor(() => expect(upload.disabled).toBe(false));
    await act(async () => {
      fireEvent.click(upload);
    });

    await waitFor(() => expect(container.textContent).toContain("REFUSAL-SENTINEL"));
    expect(container.textContent).toContain(IT_WAS_NOT_UPLOADED);
    expect(sent(idp).filter((one) => one.method === "GET")).toHaveLength(0);
  });

  test("an upload with no file or no title is not sent", () => {
    // What breaks if this is deleted: an empty body reaches the route and the person reads a
    // validation error about a field they could not see.
    expect(uploadBody("", "prices.csv", new Uint8Array([65]), "")).toBeNull();
    expect(uploadBody("Price list", "", null, "")).toBeNull();
    expect(uploadBody("Price list", "prices.csv", new Uint8Array([65]), " ")?.key_column).toBeNull();
    expect(base64Of(new Uint8Array([72, 105]))).toBe(btoa("Hi"));
    expect(readUploaded({ refused: "no", classification: null })).toEqual({ refused: "no", page: null });
  });
});

describe("marking a column of an uploaded table", () => {
  test("a mark is reviewed, then applied exactly as reviewed, and the epoch it moved is shown", async () => {
    // What breaks if this is deleted: M7.5.3's editor can apply a mark nobody reviewed, apply
    // something other than what was reviewed, or apply it without the person seeing that the
    // digest answers are cached under moved.
    let epoch = "EPOCH-BEFORE-0000";
    const { container, idp } = await mount(`/classification/${ENTITY}/margin`, (url, method) => {
      if (method === "POST" && url.endsWith("/columns/margin/marks/review")) {
        return json(reviewedMark());
      }
      if (method === "PUT" && url.endsWith("/columns/margin/marks")) {
        epoch = "EPOCH-AFTER-11111";
        return json({ applied: true, review: reviewedMark(), classification: stored(epoch) });
      }
      return method === "GET" ? json(stored(epoch)) : null;
    });
    await waitFor(() => expect(container.textContent).toContain(REVIEW_BEFORE_APPLYING));
    expect(container.textContent).not.toContain("Apply this mark");
    expect(container.querySelector(".grid__table tbody")?.textContent).toContain("derived");

    const review = [...container.querySelectorAll(".form button[type=submit]")].at(-1);
    await act(async () => {
      fireEvent.click(review as HTMLElement);
    });
    await waitFor(() => expect(container.textContent).toContain("Apply this mark"));
    const apply = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === "Apply this mark",
    );
    await act(async () => {
      fireEvent.click(apply as HTMLElement);
    });

    await waitFor(() => expect(container.textContent).toContain(IT_WAS_APPLIED));
    const calls = sent(idp);
    const reviewed = calls.find((one) => one.method === "POST");
    const applied = calls.find((one) => one.method === "PUT");
    expect(applied?.body).toEqual(reviewed?.body);
    expect(Object.keys(applied?.body as object).sort()).toEqual(
      Object.keys(declaredRequestBodySchema(MARK_OPERATION, "put").properties ?? {}).sort(),
    );
    expect(container.textContent).toContain("EPOCH-BEFORE");
    expect(container.textContent).toContain("EPOCH-AFTER");
    expect(container.textContent).toContain(WHAT_THE_EPOCH_IS);
    await waitFor(() =>
      expect(calls.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(1),
    );
    await waitFor(() =>
      expect(sent(idp).filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2),
    );
  });

  test("the mark form offers the three marks and no capability", () => {
    // What breaks if this is deleted: a capability field appears on the mark form and a column
    // marked restricted can be sent with the table grant beside it.
    const schema = columnMarkSchema(["cost", "sell_price"]);
    expect(Object.keys(schema.properties ?? {}).sort()).toEqual(["access", "derived_from"]);
    expect([...MARK_WORDS]).toEqual(["open", "restricted", "derived"]);
    expect(submittedMark({ access: "open", derived_from: [], required_capability: "read:x" })).toEqual({
      access: "open",
      derived_from: [],
    });
    expect(submittedMark({ access: "public", derived_from: [] })).toBeNull();
  });

  test("no sentence the upload and the marks add carries a number", () => {
    // What breaks if this is deleted: a count arrives in the new prose, "3 columns start
    // restricted", which is the rule this console keeps everywhere else.
    for (const sentence of [UPLOAD_HEADING, UPLOAD_LEDE, REVIEW_BEFORE_APPLYING, WHAT_THE_EPOCH_IS]) {
      expect(sentence, sentence).not.toMatch(/\d/);
    }
  });
});
