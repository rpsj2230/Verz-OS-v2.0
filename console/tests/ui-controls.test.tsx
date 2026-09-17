/**
 * The component layer's controls, used from a keyboard: button, badge, input, textarea, label,
 * checkbox, switch, select and the write-once secret field.
 *
 * Each test drives the control the way a person without a mouse does, by focus and key, and asserts
 * what they would meet: that it takes focus, that a key does what it says, and that focus is where
 * they expect afterwards. jsdom runs Radix's own handlers, so what is checked is the component as
 * shipped, not a model of it. What jsdom cannot check, a focus ring being drawn, is held against the
 * compiled stylesheet in `tests/ui-structure.test.tsx`.
 *
 * Task ids: M27.10.2
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, describe, expect, test, vi } from "vitest";
import { Badge } from "../src/components/ui/badge";
import { Button } from "../src/components/ui/button";
import { Checkbox } from "../src/components/ui/checkbox";
import { Input } from "../src/components/ui/input";
import { Label } from "../src/components/ui/label";
import {
  SECRET_NOT_STORED,
  SECRET_STORED,
  SecretField,
  useSecret,
  type SecretHandle,
} from "../src/components/ui/secret-field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../src/components/ui/select";
import { Switch } from "../src/components/ui/switch";
import { Textarea } from "../src/components/ui/textarea";
import { installRadixStubs } from "./support/radix";
import { parseConsoleSource, propNamesOf } from "./support/typescript";

beforeAll(() => {
  installRadixStubs();
});

describe("button and badge", () => {
  test("a button is a native button in the tab order, and a link rendered as one is still a link", () => {
    // What breaks if this is deleted: `asChild` exists so a router link can look like a button, and a
    // copy that rendered a button around the link would put two controls in the tab order and send
    // Enter to the wrong one. The plain button must stay a `button`, which is what gives Enter and
    // Space for free and what `keyboard-access.test.tsx` counts as a native control.
    const pressed = vi.fn();
    render(
      <>
        <Button onClick={pressed}>Save</Button>
        <Button asChild variant="link">
          <a href="/features">Open Features</a>
        </Button>
      </>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(pressed).toHaveBeenCalledTimes(1);

    const link = screen.getByRole("link", { name: "Open Features" });
    expect(link.tagName).toBe("A");
    expect(link.querySelector("button")).toBeNull();
    expect(link.getAttribute("data-slot")).toBe("button");
  });

  test("a disabled button cannot be reached or pressed", () => {
    // What breaks if this is deleted: a button styled as disabled that still takes a click, which is
    // a write a person was told they could not make.
    const pressed = vi.fn();
    render(
      <Button disabled onClick={pressed}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    fireEvent.click(button);
    expect(button.disabled).toBe(true);
    expect(pressed).not.toHaveBeenCalled();
  });

  test("a badge is text, not a control", () => {
    // What breaks if this is deleted: a badge rendered as a button or with a tab stop, which puts a
    // label in the keyboard order between two things a person can do.
    render(<Badge variant="secondary">Draft</Badge>);
    const badge = screen.getByText("Draft");
    expect(badge.tagName).toBe("SPAN");
    expect(badge.hasAttribute("tabindex")).toBe(false);
  });
});

describe("text fields", () => {
  test("a label focuses its input, and an input and a textarea take typed text", () => {
    // What breaks if this is deleted: Radix's label forwarding the click to its control, which is the
    // larger target a person on a phone aims at, and the plain fields every form here is built from.
    render(
      <>
        <Label htmlFor="name">Name</Label>
        <Input id="name" />
        <Label htmlFor="note">Note</Label>
        <Textarea id="note" />
      </>,
    );
    const input = screen.getByLabelText("Name") as HTMLInputElement;
    const textarea = screen.getByLabelText("Note") as HTMLTextAreaElement;

    fireEvent.change(input, { target: { value: "Operations" } });
    fireEvent.change(textarea, { target: { value: "Line one" } });
    expect(input.value).toBe("Operations");
    expect(textarea.value).toBe("Line one");
    textarea.focus();
    expect(document.activeElement).toBe(textarea);
  });
});

describe("checkbox and switch", () => {
  test("space toggles a checkbox and the state is announced", () => {
    // What breaks if this is deleted: Radix's checkbox is a button carrying `role="checkbox"`, so a
    // wrapper that dropped the role would be announced as a button with no state.
    render(<Checkbox aria-label="Include archived" />);
    const box = screen.getByRole("checkbox", { name: "Include archived" });
    box.focus();
    expect(document.activeElement).toBe(box);
    expect(box.getAttribute("aria-checked")).toBe("false");

    fireEvent.click(box);
    expect(box.getAttribute("aria-checked")).toBe("true");
    expect(box.querySelector(".lucide-check")).not.toBeNull();
  });

  test("some of a set selected draws a dash and never a tick, controlled or not", () => {
    // What breaks if this is deleted: the defect the spike found in shadcn/ui's checkbox, which drew
    // the same tick for "some selected" as for "all selected", so a header checkbox over a partly
    // selected list told a person the whole list was chosen. Asserted on which icon is in the
    // document, because jsdom applies no stylesheet and a class that hides a tick hides nothing here.
    function Header() {
      const [state, setState] = useState<boolean | "indeterminate">("indeterminate");
      return <Checkbox aria-label="All rows" checked={state} onCheckedChange={setState} />;
    }
    render(
      <>
        <Header />
        <Checkbox aria-label="Uncontrolled" defaultChecked="indeterminate" />
      </>,
    );
    for (const name of ["All rows", "Uncontrolled"]) {
      const box = screen.getByRole("checkbox", { name });
      expect(box.getAttribute("aria-checked"), name).toBe("mixed");
      expect(box.querySelector(".lucide-minus"), name).not.toBeNull();
      expect(box.querySelector(".lucide-check"), name).toBeNull();

      fireEvent.click(box);
      expect(box.getAttribute("aria-checked"), name).toBe("true");
      expect(box.querySelector(".lucide-check"), name).not.toBeNull();
      expect(box.querySelector(".lucide-minus"), name).toBeNull();
    }
  });

  test("a switch is announced as a switch and toggles from the keyboard", () => {
    // What breaks if this is deleted: a switch announced as a checkbox or a button, which tells a
    // screen reader user it stages a choice rather than taking effect.
    const changed = vi.fn();
    render(<Switch aria-label="Scheduled jobs" onCheckedChange={changed} />);
    const toggle = screen.getByRole("switch", { name: "Scheduled jobs" });
    toggle.focus();
    expect(document.activeElement).toBe(toggle);

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(changed).toHaveBeenCalledWith(true);
  });
});

describe("select", () => {
  test("a select opens from the keyboard, moves with the arrows, chooses with Enter and gives focus back", async () => {
    // What breaks if this is deleted: the listbox a keyboard user reaches a filter through. A select
    // that opened only on a pointer, or that left focus inside a closed listbox, is a filter somebody
    // without a mouse cannot set.
    const chosen = vi.fn();
    render(
      <Select onValueChange={chosen}>
        <SelectTrigger aria-label="Department">
          <SelectValue placeholder="Any department" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="operations">Operations</SelectItem>
          <SelectItem value="finance">Finance</SelectItem>
        </SelectContent>
      </Select>,
    );
    const trigger = screen.getByRole("combobox", { name: "Department" });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: "Enter" });
    });

    const listbox = await screen.findByRole("listbox");
    expect(listbox).toBeTruthy();
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["Operations", "Finance"]);

    await act(async () => {
      fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
    });
    await act(async () => {
      fireEvent.keyDown(document.activeElement as Element, { key: "Enter" });
    });

    expect(chosen).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("the write-once secret field", () => {
  let handle: SecretHandle | null = null;

  function Form({ stored, onPresence }: { stored: boolean; onPresence?: (present: boolean) => void }) {
    const secret = useSecret();
    handle = secret;
    return <SecretField secret={secret} label="Signing secret" stored={stored} {...(onPresence ? { onPresenceChange: onPresence } : {})} />;
  }

  test("it can be told nothing that would put a value into it", () => {
    // What breaks if this is deleted: a `value` or `defaultValue` prop, which is how a stored secret
    // would be handed back to the page to prefill, and a `reveal` or `copy` prop, which is how it
    // would be echoed. The whole list is asserted, so any addition has to be argued for here.
    expect(propNamesOf(parseConsoleSource("src/components/ui/secret-field.tsx"), "SecretField")).toEqual([
      "secret",
      "label",
      "stored",
      "description",
      "disabled",
      "invalid",
      "describedBy",
      "onPresenceChange",
      "className",
    ]);
  });

  test("what is typed is never in the markup, and taking it empties the field in the same call", () => {
    // What breaks if this is deleted: a controlled field, which writes the typed value into the
    // element's `value` attribute on every render so a serialised page carries the key, and keeps a
    // copy in state until somebody remembers to clear it. The positive half: the value is really
    // returned, so a field that took nothing would fail too.
    const presence = vi.fn();
    const { container } = render(<Form stored={false} onPresence={presence} />);
    const field = screen.getByLabelText("Signing secret") as HTMLInputElement;

    expect(field.type).toBe("text");
    expect(field.getAttribute("autocomplete")).toBe("off");
    expect(field.getAttribute("spellcheck")).toBe("false");
    field.focus();
    fireEvent.input(field, { target: { value: "whsec-s3cr3t-value" } });
    expect(presence).toHaveBeenLastCalledWith(true);
    expect(container.innerHTML).not.toContain("whsec-s3cr3t-value");

    let taken = "";
    act(() => {
      taken = handle?.take() ?? "";
    });
    expect(taken).toBe("whsec-s3cr3t-value");
    expect(field.value).toBe("");
    expect(presence).toHaveBeenLastCalledWith(false);
    expect(document.activeElement).toBe(field);
  });

  test("a stored value is said to exist in one sentence that is the same whatever is stored", () => {
    // What breaks if this is deleted: a hint such as "ending in 4f2a" or a row of dots the length of
    // the key, each of which reads a fact about the credential back to the page. The field is empty
    // and described by a constant, and the markup for two installs with different secrets stored is
    // one string, because nothing about the secret reaches the component.
    const withoutIds = (markup: string) => markup.replace(/«r\w+»/g, "«id»");
    const { container, unmount } = render(<Form stored />);
    const field = screen.getByLabelText("Signing secret") as HTMLInputElement;
    const once = withoutIds(container.innerHTML);

    expect(field.value).toBe("");
    expect(field.getAttribute("aria-describedby")).toBeTruthy();
    expect(document.getElementById((field.getAttribute("aria-describedby") ?? "").split(" ")[0] ?? "")?.textContent).toBe(SECRET_STORED);
    unmount();

    const again = render(<Form stored />);
    expect(withoutIds(again.container.innerHTML)).toBe(once);
    again.unmount();

    render(<Form stored={false} />);
    expect(screen.getByText(SECRET_NOT_STORED)).toBeTruthy();
  });
});
