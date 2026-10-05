/**
 * What the Settings row "Send the evening digest to" asks `brain.digest_routes` for, and how the
 * answer is read. No React.
 *
 * The owner decided where the digest goes in needs-rupash item 125: one setting that offers every
 * connected channel and a conversation in it, off until somebody chooses, recorded with their name.
 * So the row offers what the API lists and nothing typed: a choice is a conversation a connected
 * channel said it can post to, and the API refuses any other.
 *
 * Task ids: M38.3.3.1, M38.3.3.4
 */

import type { components } from "../api/schema";

export type DestinationBody = components["schemas"]["DestinationPage"];
export type ChannelOffer = components["schemas"]["ChannelOfferView"];

/** Where the API keeps the destination, and where a choice is saved. */
export const DIGEST_DESTINATION_API_PATH = "/digest/destination";

/** The setting whose Settings row this replaces with a choice from a list. */
export const DIGEST_DESTINATION_SETTING = "INSTALL_DIGEST_DESTINATION";

/** The list's value for switching the digest off. No channel is called this. */
export const OFF_VALUE = "off";

export const OFF_LABEL = "Off: send no evening digest";
export const READING_DESTINATION = "Asking each connected channel where it can post.";
export const NOTHING_TO_CHOOSE =
  "No connected channel offers a conversation yet. Connect a chat channel and add its bot to a group, and it is listed here.";
export const UNREADABLE_DESTINATION = "The answer could not be read as where the digest goes.";
export const DESTINATION_SAVED = "Saved. The evening digest goes where you chose.";
export const DESTINATION_NOT_SAVED = "Where the digest goes was not saved";
export const CHOOSE = "Save the choice";
export const KEEP_DESTINATION = "Keep it as it is";

/** The list value for one conversation. */
export function choiceValue(channel: string, conversation: string): string {
  return `${channel}:${conversation}`;
}

/** The value the list starts on: the current choice, or off. */
export function currentValue(body: DestinationBody): string {
  return body.channel === null || body.channel === undefined || !body.conversation
    ? OFF_VALUE
    : choiceValue(body.channel, body.conversation);
}

/** The request body for a list value: off, or the channel and conversation it names. */
export function chosenBody(value: string): { off: boolean; channel?: string; conversation?: string } {
  if (value === OFF_VALUE) {
    return { off: true };
  }
  const at = value.indexOf(":");
  return { off: false, channel: value.slice(0, at), conversation: value.slice(at + 1) };
}

/** A conversation's name as offered, or the current choice when it is not on today's list. */
export function nameOf(body: DestinationBody, value: string): string {
  if (value === OFF_VALUE) {
    return OFF_LABEL;
  }
  for (const offer of body.offers) {
    for (const one of offer.conversations) {
      if (choiceValue(one.channel, one.conversation) === value) {
        return `${one.name} (${offer.channel})`;
      }
    }
  }
  return value;
}

/** The confirmation's consequence for a choice. */
export function chooseConsequence(body: DestinationBody, value: string): string {
  return value === OFF_VALUE
    ? "No evening digest is sent until somebody chooses again. The change is recorded with your name."
    : `The evening digest goes to ${nameOf(body, value)} from its next send time. The change is recorded with your name.`;
}

/** Read `DestinationPage` out of a response body, or null when it is not one. */
export function readDestination(payload: unknown): DestinationBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { offers?: unknown; stopped_because?: unknown };
  if (!Array.isArray(body.offers) || typeof body.stopped_because !== "string") {
    return null;
  }
  return payload as DestinationBody;
}
