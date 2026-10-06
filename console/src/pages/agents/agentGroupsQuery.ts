/**
 * An agent's group chats: where it is installed and the chats the bot is in that it could go into,
 * as `GET /api/v1/agents/{id}/groups` answers, and the two writes (M39.2.4.4).
 *
 * Every field is the route's: the chat's name is the vendor's own, and nothing here names a chat by
 * its id when the vendor sent a name. A reader the route refuses gets no card at all.
 *
 * Task ids: M39.2.4.4
 */

import type { components } from "../../api/schema";

export type GroupsView = components["schemas"]["AgentGroupsView"];
export type GroupRoom = components["schemas"]["GroupRoomView"];
export type GroupInstall = components["schemas"]["GroupInstallView"];

export function agentGroupsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/groups`;
}

export function agentGroupRemovalApiPath(agentId: string): string {
  return `${agentGroupsApiPath(agentId)}/removal`;
}

/** The groups the route sent, or null when the body is not one. */
export function readGroups(payload: unknown): GroupsView | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<GroupsView>;
  if (typeof body.agent_id !== "string" || !Array.isArray(body.installs) || !Array.isArray(body.rooms)) {
    return null;
  }
  return { agent_id: body.agent_id, installs: body.installs, rooms: body.rooms };
}

/** The words a chat is shown by: the vendor's name, or a plain description when it sent none. */
export function chatName(one: { readonly name: string }): string {
  return one.name.trim() === "" ? "A group chat with no name" : one.name;
}

/** A room's value in the chooser: the channel and the vendor's reference, which the route reads. */
export function roomKey(one: GroupRoom): string {
  return `${one.channel}:${one.room_ref}`;
}
