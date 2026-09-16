/**
 * The Storage screen: each bucket with its retention and reason, where the store is, and the
 * sentences that say what is not shown.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working: a
 * bucket kept for ever drawn as kept for no days, a usage bar where nothing is measured, and a
 * control on a screen whose API offers none.
 *
 * Task ids: M27.8.15
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FROM_DEFAULT, NOT_A_READABLE_ADDRESS, READING_STORAGE } from "../src/pages/Storage";
import type { StorageBody } from "../src/pages/storageQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const LISTING = "/api/v1/storage";
const CONSOLE_ORIGIN = "https://console.test";
const USAGE = "How much each bucket holds is not measured.";
const NAMES = "No object is listed by name.";

beforeAll(async () => {
  await import("../src/pages/Storage");
}, 60_000);

function storage(overrides: Partial<StorageBody> = {}): StorageBody {
  return {
    buckets: [
      {
        name: "assets",
        holds: "console images",
        retention_days: null,
        retention_reason: "an asset is referenced by a document that outlives any window",
        versioned: false,
        public_read: false,
        kinds: ["console_asset", "knowledge_original"],
      },
      {
        name: "backups",
        holds: "database dumps",
        retention_days: 35,
        retention_reason: "one full monthly cycle plus a few days",
        versioned: true,
        public_read: false,
        kinds: ["database_dump"],
      },
    ],
    findings: [],
    endpoint: {
      address: "http://seaweedfs:8333",
      prefix: "brain",
      from_default: true,
      told: "The store's address is shown as its scheme, host and port.",
    },
    connection: "Nothing in the application reads or writes the object store yet.",
    usage: USAGE,
    names: NAMES,
    retention: "Each bucket's retention is part of the product.",
    read_at: "2019-03-04T09:00:00Z",
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function mount(answer: (url: URL) => Response | null): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answer(new URL(url, CONSOLE_ORIGIN));
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Storage } = await import("../src/pages/Storage");
  const router = createMemoryRouter([{ path: "/storage", element: <Storage /> }], {
    initialEntries: ["/storage"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_STORAGE)) {
      throw new Error("still reading");
    }
  });
  return container;
}

describe("what the storage screen shows", () => {
  test("each bucket reads as what it holds, for how long, why, and whether it is versioned", async () => {
    // What breaks if this is deleted: a bucket kept until deleted drawn as kept for no days, or the
    // reason for a retention dropped from the one screen that shows it.
    const container = await mount((url) => (url.pathname === LISTING ? json(storage()) : null));
    const table = container.querySelector('[aria-label="Buckets"]')?.textContent ?? "";
    expect(table).toContain("Until deleted");
    expect(table).toContain("35 days");
    expect(table).toContain("one full monthly cycle plus a few days");
    expect(table).toContain("knowledge_original");
    expect(container.textContent).toContain("http://seaweedfs:8333");
    expect(container.textContent).toContain(FROM_DEFAULT);
  });

  test("usage and object names are sentences, and the screen has no control", async () => {
    // What breaks if this is deleted: a usage bar drawn over a figure nothing measures, or a button
    // on a screen whose API offers no write.
    const container = await mount((url) => (url.pathname === LISTING ? json(storage()) : null));
    expect(container.textContent).toContain(USAGE);
    expect(container.textContent).toContain(NAMES);
    expect(container.querySelectorAll("button, input, select, progress, meter")).toHaveLength(0);
  });

  test("an address the API could not read is said in words, and a refusal is the API's message", async () => {
    // What breaks if this is deleted: an empty cell where the address should be, or a 404 drawn as
    // an install with no buckets.
    const unreadable = await mount((url) =>
      url.pathname === LISTING
        ? json(storage({ endpoint: { address: null, prefix: "", from_default: false, told: "shown" } }))
        : null,
    );
    expect(unreadable.textContent).toContain(NOT_A_READABLE_ADDRESS);

    const refused = await mount((url) =>
      url.pathname === LISTING ? json({ message: "I could not find that.", trace_id: "t-1" }, 404) : null,
    );
    expect(refused.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.textContent).toContain("I could not find that.");
    expect(refused.querySelector('[aria-label="Buckets"]')).toBeNull();
  });
});
