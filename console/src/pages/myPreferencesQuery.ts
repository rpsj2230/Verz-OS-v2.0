/**
 * What the settings card in My workspace asks the API for and what it sends. No React.
 *
 * `brain.member_preference_routes` answers for the person asking and nobody else and takes no
 * parameter naming a person. The page offers what the API says is open (the channels they are
 * connected on, the places an approval may wait) and sends the whole of where they are reached in
 * one request, because a half-saved reach is two settings that disagree.
 *
 * Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
 */

import type { components } from "../api/schema";

export type Preferences = components["schemas"]["PreferencesView"];
export type ChannelSetting = components["schemas"]["ChannelSettingView"];

export const PREFERENCES_API_PATH = "/me/preferences";
export const LEARNING_API_PATH = "/me/preferences/learning";
export const REACH_API_PATH = "/me/preferences/reach";
export const QUIET_API_PATH = "/me/preferences/quiet-hours";

/** What switching learning off or on sends. */
export function learningBody(optedOut: boolean): { readonly opted_out: boolean } {
  return { opted_out: optedOut };
}

/** What a person has typed for where they are reached. Strings, as a form holds them. */
export interface ReachDraft {
  readonly primary: string;
  readonly approvalRoute: string;
  /** Channel name to the kinds ticked for it. A channel with nothing ticked is not sent. */
  readonly notify: Readonly<Record<string, readonly string[]>>;
}

/** The draft a saved answer starts from. */
export function draftOf(saved: Preferences): ReachDraft {
  return {
    primary: saved.primary ?? "",
    approvalRoute: saved.approval_route ?? "",
    notify: Object.fromEntries(saved.channels.filter((one) => one.chosen).map((one) => [one.channel, one.notify])),
  };
}

/** The body the whole reach is sent as: empty strings are left out, a channel with a statement is kept. */
export function reachBody(draft: ReachDraft): {
  readonly primary: string | null;
  readonly approval_route: string | null;
  readonly notices: readonly { readonly channel: string; readonly notify: readonly string[] }[];
} {
  return {
    primary: draft.primary === "" ? null : draft.primary,
    approval_route: draft.approvalRoute === "" ? null : draft.approvalRoute,
    notices: Object.entries(draft.notify).map(([channel, notify]) => ({ channel, notify })),
  };
}

/** Whether a kind is ticked for a channel in this draft. */
export function ticked(draft: ReachDraft, channel: string, kind: string): boolean {
  return (draft.notify[channel] ?? []).includes(kind);
}

/** The draft with one kind ticked or cleared for a channel. Ticking none still states a choice. */
export function toggled(draft: ReachDraft, channel: string, kind: string, on: boolean): ReachDraft {
  const now = draft.notify[channel] ?? [];
  const next = on ? [...new Set([...now, kind])].sort() : now.filter((one) => one !== kind);
  return { ...draft, notify: { ...draft.notify, [channel]: next } };
}
