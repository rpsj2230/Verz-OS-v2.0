/**
 * Choosing an item from a row's menu the way a keyboard user does, which is the one way Radix's
 * menu opens under jsdom: a click is a pointer event jsdom does not dispatch as Radix listens for.
 * `tests/agents-page.test.tsx` wrote this first; the Governance page tests share it.
 *
 * Task ids: none
 */

import { act, fireEvent, screen, within } from "@testing-library/react";

export async function chooseInMenu(trigger: HTMLElement, label: string): Promise<void> {
  trigger.focus();
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  const menu = await screen.findByRole("menu");
  const item = within(menu).getByRole("menuitem", { name: label });
  item.focus();
  await act(async () => {
    fireEvent.keyDown(item, { key: "Enter" });
  });
}

/** Presses the confirmation dialog's act, by its label. */
export async function confirmWith(label: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
  });
}
