/**
 * A page's statement that a write took effect is also announced in the toast region, and the shell
 * mounts that region once (M27.10.2).
 *
 * Thirty-eight places say "done" with a `Note kind="done"`. Announcing from the note gives every one
 * of them the toast without an edit to each page, so the tests below hold the note, not a page: the
 * note announces a sentence, announces only a done note, and keeps its own line on the page. The
 * shell test holds the other half, that the region exists in the shell and is not a part nothing
 * draws.
 *
 * Task ids: M27.10.2
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { toast } from "sonner";
import { Note } from "../src/components/kit";
import { Toaster, TOAST_REGION_LABEL } from "../src/components/ui/sonner";
import { readConsoleFile } from "./support/repo";
import { consoleSourcePaths } from "./support/typescript";

beforeEach(() => {
  // jsdom has no `matchMedia`, which sonner asks when the theme is "system".
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
  }));
});

afterEach(() => {
  toast.dismiss();
});

function region(): HTMLElement {
  return screen.getByRole("region", { name: new RegExp(TOAST_REGION_LABEL) });
}

describe("a done note is announced as well as drawn", () => {
  test("a done note's sentence appears in the toast region and the note stays on the page", async () => {
    // What breaks if this is deleted: the toast region is mounted and nothing ever sends to it, so
    // the page-kit part that is meant to announce a write announces none.
    render(
      <>
        <Toaster />
        <Note kind="done">The webhook was switched off.</Note>
      </>,
    );
    await waitFor(() => expect(region().textContent).toContain("The webhook was switched off."));
    expect(document.querySelector('[data-slot="note"]')?.textContent).toContain("The webhook was switched off.");
  });

  test("a note that is not a done note announces nothing", async () => {
    // What breaks if this is deleted: a toast for every information line on every page, which is
    // the noise that teaches a person to ignore the region. The sibling above proves it speaks.
    render(
      <>
        <Toaster />
        <Note kind="info">Nothing has been changed.</Note>
        <Note kind="attention">Look at this.</Note>
      </>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(region().textContent).not.toContain("Nothing has been changed.");
    expect(region().textContent).not.toContain("Look at this.");
  });

  test("a done note drawn twice with the same sentence announces it once while it shows", async () => {
    // What breaks if this is deleted: a page that draws its note again on every refresh stacks the
    // same toast over and over, because the sentence is the toast's id.
    render(
      <>
        <Toaster />
        <Note kind="done">Saved.</Note>
        <Note kind="done">Saved.</Note>
      </>,
    );
    await waitFor(() => expect(region().textContent).toContain("Saved."));
    expect(region().textContent?.split("Saved.").length).toBe(2);
  });

  test("a done note holding markup rather than a sentence is not turned into text", async () => {
    // What breaks if this is deleted: a toast reading "[object Object]" for a note built from parts.
    render(
      <>
        <Toaster />
        <Note kind="done">
          <b>Saved</b> now.
        </Note>
      </>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(region().textContent).not.toContain("object");
    expect(region().textContent).not.toContain("Saved");
  });
});

describe("the region draws where the browser cannot say what the machine prefers", () => {
  test("a toaster rendered with no matchMedia draws instead of throwing", () => {
    // What breaks if this is deleted: the region is mounted in the shell, so a missing matchMedia
    // (any test document, and an embedded view without it) takes the whole page down with the toast
    // region it was meant to serve. The sibling tests above stub matchMedia and prove it speaks.
    vi.stubGlobal("matchMedia", undefined);
    render(<Toaster />);
    expect(region().getAttribute("aria-live")).toBe("polite");
  });
});

describe("the shell mounts the region once", () => {
  test("the shell draws the toaster, and nothing else in the console mounts a second", () => {
    // What breaks if this is deleted: `ui/sonner.tsx` says the region is mounted once, near the
    // root, and for ever nothing mounted it, so the toast part existed and no page could be heard
    // in it. Read as the source's import and element, not a word in a comment.
    const shell = readConsoleFile("src/layout/Shell.tsx");
    expect(shell).toMatch(/import \{ Toaster \} from "..\/components\/ui\/sonner";/);
    expect(shell).toMatch(/<Toaster \/>/);
    const mounting = consoleSourcePaths("src").filter((file) => /<Toaster[\s/>]/.test(readConsoleFile(file)));
    expect(mounting).toEqual(["src/layout/Shell.tsx"]);
  });
});
