/**
 * The component layer's overlays, used from a keyboard: dialog, confirmation, drawer, popover, menu,
 * tooltip, command palette and the toast region.
 *
 * **Focus return is the property these tests exist for.** An overlay that closes and leaves focus on
 * `<body>` puts a keyboard user back at the top of the page with no record of where they were. Radix
 * gets it right when a dialog is opened by its own trigger and wrong when it is opened from state,
 * which is how a confirmation opened by a menu item and a palette opened by a key both work; the
 * design spike measured `<body>` in Chrome for both. `components/ui/focus-return.ts` is the fix and
 * the tests below open every dialog-shaped overlay both ways.
 *
 * Task ids: M27.10.2
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { beforeAll, describe, expect, test, vi } from "vitest";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../src/components/ui/alert-dialog";
import { Button } from "../src/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "../src/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "../src/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../src/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "../src/components/ui/popover";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "../src/components/ui/sheet";
import { Toaster, TOAST_REGION_LABEL } from "../src/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../src/components/ui/tooltip";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

function escape(): void {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
}

/** A button that opens an overlay from state, which is the case Radix does not return focus for. */
function OpenedFromState({ children }: { children: (open: boolean, setOpen: (open: boolean) => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open from state
      </button>
      {children(open, setOpen)}
    </>
  );
}

describe("dialog", () => {
  test("a dialog opened by its trigger takes focus inside and gives it back on Escape", async () => {
    // What breaks if this is deleted: the ordinary case, which Radix handles, and which is the
    // sibling that proves the fix below did not break it.
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Rename</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Rename the agent</DialogTitle>
          <DialogDescription>The name people see.</DialogDescription>
          <input aria-label="Name" />
        </DialogContent>
      </Dialog>,
    );
    const trigger = screen.getByRole("button", { name: "Rename" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = await screen.findByRole("dialog", { name: "Rename the agent" });
    expect(dialog.contains(document.activeElement)).toBe(true);

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("a dialog opened from state gives focus back to whatever opened it", async () => {
    // What breaks if this is deleted: the fix in `focus-return.ts`. Without it Radix focuses a trigger
    // that does not exist and focus falls to `<body>`, measured in Chrome by the design spike.
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent>
              <DialogTitle>Details</DialogTitle>
              <DialogDescription>Facts about the row.</DialogDescription>
            </DialogContent>
          </Dialog>
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByRole("dialog", { name: "Details" });

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  test("a dialog whose opener is gone gives focus to the element it was told to", async () => {
    // What breaks if this is deleted: `returnFocusTo`, for a dialog opened by a menu item that no
    // longer exists by the time the dialog closes. Without it focus goes to `<body>` again, and the
    // page cannot say where it should have gone.
    function Row({ openerGone }: { openerGone: boolean }) {
      const [open, setOpen] = useState(false);
      const actions = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button type="button" ref={actions}>
            Actions for this row
          </button>
          {openerGone ? null : (
            <button type="button" onClick={() => setOpen(true)}>
              Archive
            </button>
          )}
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent returnFocusTo={actions.current}>
              <DialogTitle>Archive this row</DialogTitle>
              <DialogDescription>It leaves the list.</DialogDescription>
            </DialogContent>
          </Dialog>
        </>
      );
    }
    const { rerender } = render(<Row openerGone={false} />);
    const item = screen.getByRole("button", { name: "Archive" });
    item.focus();
    fireEvent.click(item);
    await screen.findByRole("dialog", { name: "Archive this row" });
    // The item goes while the dialog is up, as a menu's item does when its menu closes behind it: the
    // dialog saw it focused, and it is gone by the time the dialog closes.
    rerender(<Row openerGone />);
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Actions for this row" }));
  });
});

describe("confirmation", () => {
  test("a confirmation opens on the safe choice, Escape takes it, and focus goes back to the opener", async () => {
    // What breaks if this is deleted: a confirmation that opens with focus on the destructive button
    // is one Enter away from the thing it exists to slow down, and one that acts on Escape is not a
    // confirmation. Opened from state, because a confirmation is usually opened by a menu item.
    const confirmed = vi.fn();
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <AlertDialog open={open} onOpenChange={setOpen}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Archive Ticket triage?</AlertDialogTitle>
                <AlertDialogDescription>It stops answering and keeps its history.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep as it is</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={confirmed}>
                  Archive
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);

    await screen.findByRole("alertdialog", { name: "Archive Ticket triage?" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Keep as it is" }));

    escape();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(confirmed).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });
});

describe("drawer", () => {
  test("a drawer opened from state holds focus inside and gives it back to the opener", async () => {
    // What breaks if this is deleted: the create sheet on a list page, which is opened by a button
    // that sets state. Tab must stay inside it while it is open, and closing it must put a keyboard
    // user back on the button they pressed rather than at the top of the list.
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetContent>
              <SheetTitle>New webhook</SheetTitle>
              <SheetDescription>Where the events go.</SheetDescription>
              <input aria-label="Address" />
            </SheetContent>
          </Sheet>
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);

    const sheet = await screen.findByRole("dialog", { name: "New webhook" });
    expect(sheet.contains(document.activeElement)).toBe(true);
    expect(screen.getByRole("button", { name: "Close" })).toBeTruthy();

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
  });
});

describe("popover, menu and tooltip", () => {
  test("a popover closes on Escape and gives focus back to its trigger", async () => {
    // What breaks if this is deleted: a filter popover that closes and leaves focus inside a panel
    // that no longer exists.
    render(
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline">Filters</Button>
        </PopoverTrigger>
        <PopoverContent>
          <input aria-label="Owner" />
        </PopoverContent>
      </Popover>,
    );
    const trigger = screen.getByRole("button", { name: "Filters" });
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByRole("dialog");

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("a menu opens from the keyboard, moves with the arrows, acts on Enter and gives focus back", async () => {
    // What breaks if this is deleted: a row's actions menu, which a keyboard user reaches by Tab and
    // must be able to open, move through and leave without a pointer.
    const renamed = vi.fn();
    const archived = vi.fn();
    render(
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost">Actions for Ticket triage</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={renamed}>Rename</DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={archived}>
            Archive
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    const trigger = screen.getByRole("button", { name: "Actions for Ticket triage" });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: "Enter" });
    });

    await screen.findByRole("menu");
    const [rename, archive] = screen.getAllByRole("menuitem");
    await waitFor(() => expect(document.activeElement).toBe(rename));
    await act(async () => {
      fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
    });
    await waitFor(() => expect(document.activeElement).toBe(archive));

    await act(async () => {
      fireEvent.keyDown(document.activeElement as Element, { key: "Enter" });
    });
    expect(archived).toHaveBeenCalledTimes(1);
    expect(renamed).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("a tooltip appears on keyboard focus and Escape dismisses it", async () => {
    // What breaks if this is deleted: a label that only a pointer can see. A tooltip reached by Tab
    // must show, and must go away without moving focus.
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="icon" aria-label="Stop every agent">
              S
            </Button>
          </TooltipTrigger>
          <TooltipContent>Stop every agent</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    const trigger = screen.getByRole("button", { name: "Stop every agent" });
    await act(async () => {
      trigger.focus();
    });
    expect(await screen.findByRole("tooltip")).toBeTruthy();

    escape();
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });
});

describe("command palette", () => {
  test("the palette filters what it was handed, moves with the arrows, opens on Enter and gives focus back", async () => {
    // What breaks if this is deleted: global search's keyboard path. The palette is opened from state
    // by a key, so without the focus fix closing it drops focus on `<body>`; and a palette that could
    // not be driven by arrow keys and Enter is a search box with a list under it.
    const opened = vi.fn();
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <CommandDialog open={open} onOpenChange={setOpen}>
            <CommandInput placeholder="Search" />
            <CommandList>
              <CommandEmpty>Nothing matches.</CommandEmpty>
              <CommandGroup heading="Go to">
                <CommandItem onSelect={() => opened("people")}>People</CommandItem>
                <CommandItem onSelect={() => opened("agents")}>Agents</CommandItem>
                <CommandItem onSelect={() => opened("audit")}>Audit</CommandItem>
              </CommandGroup>
            </CommandList>
          </CommandDialog>
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);

    await screen.findByRole("dialog", { name: "Search the console" });
    const input = screen.getByRole("combobox");
    await waitFor(() => expect(document.activeElement).toBe(input));
    await act(async () => {
      fireEvent.change(input, { target: { value: "a" } });
    });
    const shown = screen.getAllByRole("option").map((option) => option.textContent);
    expect(shown).toEqual(["Agents", "Audit"]);

    await act(async () => {
      fireEvent.keyDown(input, { key: "ArrowDown" });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter" });
    });
    expect(opened).toHaveBeenCalledWith("audit");

    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
  });
});

describe("toast region", () => {
  test("the toast region is a labelled live region that exists before its first message", async () => {
    // What breaks if this is deleted: a region inserted at the moment its first toast arrives, which
    // some screen readers announce and others do not. The region is in the document from the first
    // render, named in the page's language, and a message sent to it is readable inside it.
    // jsdom has no `matchMedia`, which sonner asks when the theme is "system"; a machine that prefers
    // light is the stand-in, and the theme's own tests hold which theme is chosen.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
    }));
    render(<Toaster />);
    const region = screen.getByRole("region", { name: new RegExp(TOAST_REGION_LABEL) });
    expect(region.getAttribute("aria-live")).toBe("polite");

    await act(async () => {
      toast("Webhook saved");
    });
    await waitFor(() => expect(region.textContent).toContain("Webhook saved"));
  });
});
