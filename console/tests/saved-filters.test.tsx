/**
 * A person's saved filters: kept in their own browser under their own identity, never a count,
 * never a secret, and never able to throw.
 *
 * **The storage is tested as a producer and the toolbar as its consumer**, so a test of what the
 * toolbar draws is not also a test of what the store holds: the first half reads and writes the
 * module with a stand-in storage, the second mounts the toolbar and presses its buttons against the
 * browser's own (jsdom's), and reads back what was kept through the module.
 *
 * Task ids: M27.16.3
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, test } from "vitest";
import { CallerProvider, readCallerId } from "../src/components/kit/caller";
import { ListToolbar } from "../src/components/kit";
import {
  COULD_NOT_KEEP,
  FULL_SENTENCE,
  NAME_LABEL,
  NEEDS_A_NAME,
  NOTHING_SAVED,
  SAVED_FILTERS_LABEL,
  SAVE_LABEL,
} from "../src/components/kit/SavedFilters";
import {
  MAX_NAME,
  MAX_SAVED,
  STORAGE_PREFIX,
  fitToList,
  forgetFilter,
  keyFor,
  readSavedFilters,
  saveFilter,
  type StorageLike,
} from "../src/components/kit/savedFilterStore";
import { NO_QUESTION, type ListQuestion } from "../src/components/listing";
import type { Listing } from "../src/components/useListing";
import { installRadixStubs } from "./support/radix";

/** Far from any wall clock and any real person: the key carries the identity, not a time. */
const ADA = "p-ada-0001";
const BOB = "p-bob-0002";
const LIST = "/agents|Narrow the agents";
const ASKED: ListQuestion = { search: "ticket", filters: { state: "enabled" }, sort: "department" };

/** A storage that holds a map, so a test can read exactly what was written and where. */
function memory(): StorageLike & { readonly held: Map<string, string> } {
  const held = new Map<string, string>();
  return {
    held,
    getItem: (key) => held.get(key) ?? null,
    setItem: (key, value) => {
      held.set(key, value);
    },
  };
}

describe("what is kept", () => {
  test("a question saved by one person is read back for them and for nobody else", () => {
    // What breaks if this is deleted: the shared-computer case, where the next person to sign in on
    // a browser is shown the searches of the one before, which can name a customer, a colleague or a
    // case. The key carries the principal.
    const store = memory();
    expect(saveFilter(ADA, LIST, "Enabled tickets", ASKED, store).saved).toBe(true);
    expect(readSavedFilters(ADA, LIST, store)).toEqual([{ name: "Enabled tickets", question: ASKED }]);
    expect(readSavedFilters(BOB, LIST, store)).toEqual([]);
    expect(readSavedFilters(ADA, "/skills|Narrow the skills", store)).toEqual([]);
    expect([...store.held.keys()]).toEqual([keyFor(ADA, LIST)]);
    expect(keyFor(ADA, LIST).startsWith(STORAGE_PREFIX)).toBe(true);
  });

  test("saving under a name already kept replaces it, and an eleventh name is refused rather than dropping one", () => {
    // What breaks if this is deleted: saving again duplicates the entry, or the eleventh silently
    // pushes out one the person chose to keep, which they discover the day they need it.
    const store = memory();
    saveFilter(ADA, LIST, "Mine", { ...NO_QUESTION, search: "one" }, store);
    saveFilter(ADA, LIST, "Mine", { ...NO_QUESTION, search: "two" }, store);
    expect(readSavedFilters(ADA, LIST, store)).toEqual([{ name: "Mine", question: { search: "two", filters: {}, sort: "" } }]);
    for (let index = 1; index < MAX_SAVED; index += 1) {
      expect(saveFilter(ADA, LIST, `Filter ${String(index)}`, { ...NO_QUESTION, search: `s${String(index)}` }, store).saved).toBe(true);
    }
    const full = saveFilter(ADA, LIST, "One too many", { ...NO_QUESTION, search: "late" }, store);
    expect(full).toMatchObject({ saved: false, why: "full" });
    expect(readSavedFilters(ADA, LIST, store)).toHaveLength(MAX_SAVED);
    expect(readSavedFilters(ADA, LIST, store).some((one) => one.name === "One too many")).toBe(false);
    // Replacing one of the ten is still allowed when the list is full.
    expect(saveFilter(ADA, LIST, "Mine", { ...NO_QUESTION, search: "three" }, store).saved).toBe(true);
  });

  test("nothing is saved without a name or without a question, and a name is cut at its limit", () => {
    // What breaks if this is deleted: an entry with no name that cannot be pressed, an entry that
    // asks nothing, or a name long enough to break the popover.
    const store = memory();
    expect(saveFilter(ADA, LIST, "   ", ASKED, store)).toMatchObject({ saved: false, why: "no-name" });
    expect(saveFilter(ADA, LIST, "Empty", NO_QUESTION, store)).toMatchObject({ saved: false, why: "nothing-to-save" });
    expect(saveFilter(ADA, LIST, "Sort only", { ...NO_QUESTION, sort: "department" }, store)).toMatchObject({ saved: false, why: "nothing-to-save" });
    expect(store.held.size).toBe(0);
    const long = "n".repeat(MAX_NAME + 40);
    saveFilter(ADA, LIST, long, ASKED, store);
    expect(readSavedFilters(ADA, LIST, store)[0]?.name).toHaveLength(MAX_NAME);
  });

  test("an entry that is not exactly what was written is dropped and the rest are kept", () => {
    // What breaks if this is deleted: the browser's storage is writable by anything on this origin
    // and by a person with the tools open, so a read that trusts it lets a malformed entry throw in
    // the toolbar or carry a value the page would then send to a route.
    const store = memory();
    store.setItem(
      keyFor(ADA, LIST),
      JSON.stringify([
        { name: "Good", search: "ok", filters: { state: "enabled" }, sort: "" },
        { name: "", search: "no name", filters: {}, sort: "" },
        { name: "Number search", search: 4, filters: {}, sort: "" },
        { name: "Array filters", search: "x", filters: ["a"], sort: "" },
        { name: "Object value", search: "x", filters: { state: { deep: 1 } }, sort: "" },
        "a string",
        null,
      ]),
    );
    expect(readSavedFilters(ADA, LIST, store).map((one) => one.name)).toEqual(["Good"]);
    store.setItem(keyFor(ADA, LIST), "{not json");
    expect(readSavedFilters(ADA, LIST, store)).toEqual([]);
    store.setItem(keyFor(ADA, LIST), JSON.stringify({ name: "An object, not a list" }));
    expect(readSavedFilters(ADA, LIST, store)).toEqual([]);
  });

  test("storage that is absent, full or refuses to be read neither throws nor pretends to have saved", () => {
    // What breaks if this is deleted: a private window or a blocked-site-data browser takes the whole
    // list page down with an exception from `localStorage`, or tells the person it saved what it
    // could not.
    const refusing: StorageLike = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
    };
    expect(readSavedFilters(ADA, LIST, null)).toEqual([]);
    expect(readSavedFilters(ADA, LIST, refusing)).toEqual([]);
    expect(saveFilter(ADA, LIST, "Mine", ASKED, null)).toMatchObject({ saved: false, why: "unavailable" });
    expect(saveFilter(ADA, LIST, "Mine", ASKED, refusing)).toMatchObject({ saved: false, why: "unavailable" });
    expect(forgetFilter(ADA, LIST, "Mine", refusing)).toEqual([]);
  });

  test("forgetting removes one entry and forgetting one that is not there changes nothing", () => {
    // What breaks if this is deleted: a forget that clears every entry, or one that rewrites storage
    // for a name that was never there.
    const store = memory();
    saveFilter(ADA, LIST, "A", { ...NO_QUESTION, search: "a" }, store);
    saveFilter(ADA, LIST, "B", { ...NO_QUESTION, search: "b" }, store);
    expect(forgetFilter(ADA, LIST, "A", store).map((one) => one.name)).toEqual(["B"]);
    expect(forgetFilter(ADA, LIST, "Missing", store).map((one) => one.name)).toEqual(["B"]);
    expect(readSavedFilters(ADA, LIST, store).map((one) => one.name)).toEqual(["B"]);
  });

  test("a saved filter is cut to the columns and orders the list offers today", () => {
    // What breaks if this is deleted: a saved filter from before a page lost a column sends a
    // parameter the route does not take, which FastAPI drops without a word and the person reads as
    // the filter having worked.
    const saved = { name: "Old", question: { search: "ticket", filters: { state: "enabled", gone: "x" }, sort: "retired-order" } };
    expect(fitToList(saved, ["state"], ["", "department"])).toEqual({ search: "ticket", filters: { state: "enabled" }, sort: "" });
    expect(fitToList({ ...saved, question: { ...saved.question, sort: "department" } }, ["state"], ["", "department"]).sort).toBe("department");
  });

  test("the caller is read from a /me body only when it names one", () => {
    // What breaks if this is deleted: a body without a principal reads as a caller called "undefined",
    // and every person with such a body shares one key.
    expect(readCallerId({ principal_id: ADA })).toBe(ADA);
    expect(readCallerId({ principal_id: "" })).toBeNull();
    expect(readCallerId({ principal_id: 4 })).toBeNull();
    expect(readCallerId(null)).toBeNull();
    expect(readCallerId("p")).toBeNull();
  });
});

// -------------------------------------------------------------------------------- the control

beforeAll(() => {
  installRadixStubs();
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function listingOf(question: ListQuestion, ask: (next: ListQuestion) => void): Listing<{ state: string }> {
  return {
    body: null,
    rows: [],
    failure: null,
    busy: false,
    more: false,
    fetchingMore: false,
    moreFailure: null,
    showMore: () => {},
    question,
    ask,
    offered: { state: ["enabled", "disabled"] },
  };
}

function Harness({ person, asked }: { readonly person: string | null; readonly asked: ListQuestion[] }) {
  const [question, setQuestion] = useState<ListQuestion>(NO_QUESTION);
  const listing = listingOf(question, (next) => {
    asked.push(next);
    setQuestion(next);
  });
  return (
    <MemoryRouter initialEntries={["/agents"]}>
      <CallerProvider value={person}>
        <ListToolbar
          label="Narrow the agents"
          listing={listing}
          choices={[{ column: "state", label: "Status", everything: "Any status", read: (row) => row.state }]}
          sorts={[
            { value: "", label: "Name" },
            { value: "department", label: "Department" },
          ]}
        />
      </CallerProvider>
    </MemoryRouter>
  );
}

async function openSaved(): Promise<HTMLElement> {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SAVED_FILTERS_LABEL) }));
  });
  return await screen.findByRole("dialog");
}

/** Close the popover the way a keyboard does. */
async function closeSaved(): Promise<void> {
  await act(async () => {
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  });
}

describe("the control", () => {
  test("it is drawn for a known person and not at all without one", () => {
    // What breaks if this is deleted: a control that keeps things under nobody, which on a shared
    // browser is the same key for everyone.
    const { unmount } = render(<Harness person={ADA} asked={[]} />);
    expect(screen.getByRole("button", { name: new RegExp(SAVED_FILTERS_LABEL) })).toBeTruthy();
    unmount();
    render(<Harness person={null} asked={[]} />);
    expect(screen.queryByRole("button", { name: new RegExp(SAVED_FILTERS_LABEL) })).toBeNull();
  });

  test("a search is saved under a name, asked again with one press, and forgotten", async () => {
    // What breaks if this is deleted: the feature itself: a person types a search, saves it, clears
    // the list, and has to type it again.
    const asked: ListQuestion[] = [];
    render(<Harness person={ADA} asked={asked} />);
    const form = screen.getByRole("search", { name: "Narrow the agents" });
    fireEvent.change(within(form).getByRole("searchbox"), { target: { value: "ticket" } });
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "enabled" } });

    let popover = await openSaved();
    expect(within(popover).getByText(NOTHING_SAVED)).toBeTruthy();
    fireEvent.change(within(popover).getByLabelText(NAME_LABEL), { target: { value: "Enabled tickets" } });
    fireEvent.click(within(popover).getByRole("button", { name: SAVE_LABEL }));
    expect(readSavedFilters(ADA, "/agents|Narrow the agents").map((one) => one.name)).toEqual(["Enabled tickets"]);
    expect(within(popover).getByRole("button", { name: "Enabled tickets" })).toBeTruthy();

    // Clear everything, then ask the saved question again.
    await closeSaved();
    fireEvent.click(within(form).getByRole("button", { name: /Clear search and filters/ }));
    expect(asked.at(-1)).toEqual({ search: "", filters: {}, sort: "" });
    popover = await openSaved();
    await act(async () => {
      fireEvent.click(within(popover).getByRole("button", { name: "Enabled tickets" }));
    });
    expect(asked.at(-1)).toEqual({ search: "ticket", filters: { state: "enabled" }, sort: "" });

    popover = await openSaved();
    fireEvent.click(within(popover).getByRole("button", { name: "Forget Enabled tickets" }));
    expect(readSavedFilters(ADA, "/agents|Narrow the agents")).toEqual([]);
    expect(within(popover).getByText(NOTHING_SAVED)).toBeTruthy();
  });

  test("a person never sees a number or a value in the control, only the names they wrote", async () => {
    // What breaks if this is deleted: DENIED and ABSENT stop being the same. A control that drew a
    // count of saved filters, of matches, or the value a filter holds would show a person a figure or
    // a name they were not shown on the list.
    const store = localStorage;
    saveFilter(ADA, "/agents|Narrow the agents", "Sales only", { ...NO_QUESTION, filters: { state: "SECRET-DEPARTMENT-SENTINEL" } }, store);
    render(<Harness person={ADA} asked={[]} />);
    const popover = await openSaved();
    const text = popover.textContent ?? "";
    expect(text).toContain("Sales only");
    expect(text).not.toContain("SECRET-DEPARTMENT-SENTINEL");
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/\bof\b|total|results|matches/i);
  });

  test("applying a filter on a value nothing matches asks the route and says nothing a missing value would not", async () => {
    // What breaks if this is deleted: a hidden value answering differently from an absent one.
    // The toolbar only sends the question; the sentence for a question that matches nothing is the
    // list's own and is the same whether the value exists or not.
    saveFilter(ADA, "/agents|Narrow the agents", "Gone", { ...NO_QUESTION, filters: { state: "never-existed" } }, localStorage);
    const asked: ListQuestion[] = [];
    render(<Harness person={ADA} asked={asked} />);
    const popover = await openSaved();
    await act(async () => {
      fireEvent.click(within(popover).getByRole("button", { name: "Gone" }));
    });
    expect(asked.at(-1)).toEqual({ search: "", filters: { state: "never-existed" }, sort: "" });
  });

  test("a refused save says so in words, and saving is not offered for a list nobody has narrowed", async () => {
    // What breaks if this is deleted: a person who saves with no name sees nothing happen, or is
    // offered a save form for the whole unnarrowed list.
    const asked: ListQuestion[] = [];
    render(<Harness person={ADA} asked={asked} />);
    let popover = await openSaved();
    expect(within(popover).queryByRole("button", { name: SAVE_LABEL })).toBeNull();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ticket" } });
    popover = await openSaved();
    fireEvent.click(within(popover).getByRole("button", { name: SAVE_LABEL }));
    expect(within(popover).getByText(NEEDS_A_NAME)).toBeTruthy();
    expect(readSavedFilters(ADA, "/agents|Narrow the agents")).toEqual([]);
  });

  test("storage that refuses is said in words and the list keeps working", async () => {
    // What breaks if this is deleted: a person told "Saved." for a filter the browser refused to
    // keep, or the toolbar throwing out of the page.
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error("full");
    };
    try {
      render(<Harness person={ADA} asked={[]} />);
      fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ticket" } });
      const popover = await openSaved();
      fireEvent.change(within(popover).getByLabelText(NAME_LABEL), { target: { value: "Mine" } });
      fireEvent.click(within(popover).getByRole("button", { name: SAVE_LABEL }));
      expect(within(popover).getByText(COULD_NOT_KEEP)).toBeTruthy();
      expect(within(popover).queryByText("Saved.")).toBeNull();
    } finally {
      Storage.prototype.setItem = original;
    }
  });

  test("a full list refuses the eleventh in words", async () => {
    // What breaks if this is deleted: the save button looking dead on a full list with no reason.
    for (let index = 0; index < MAX_SAVED; index += 1) {
      saveFilter(ADA, "/agents|Narrow the agents", `Kept ${String(index)}`, { ...NO_QUESTION, search: `s${String(index)}` }, localStorage);
    }
    render(<Harness person={ADA} asked={[]} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "another" } });
    const popover = await openSaved();
    fireEvent.change(within(popover).getByLabelText(NAME_LABEL), { target: { value: "Eleventh" } });
    const button = within(popover).getByRole("button", { name: SAVE_LABEL }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(within(popover).getByText(FULL_SENTENCE)).toBeTruthy();
  });
});
