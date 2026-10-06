/**
 * The group chats an agent is installed into, on its Profile, and the confirmed install and removal
 * (M39.2.4.4).
 *
 * **The card is drawn from `GET /agents/{id}/groups` and from nothing else**, which opens to whoever
 * may switch the agent's channels and is the one 404 for anybody else, so a reader it refuses gets no
 * card at all. The chats offered are the ones the bot is in, as the vendor named them, on channels
 * this agent answers on; nobody types a chat's id.
 *
 * **Both writes go through `kit/ConfirmDialog`**: installing changes which agent answers in a chat for
 * everybody in it, and removing stops it. Neither changes what may be said there, which is the room's
 * floor whichever agent answers, and the confirmation says so.
 *
 * Task ids: M39.2.4.4
 */

import { MessagesSquare } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { NativeSelect } from "../access/formParts";
import { readNotChanged } from "../agentLifecycleQuery";
import {
  agentGroupRemovalApiPath,
  agentGroupsApiPath,
  chatName,
  readGroups,
  roomKey,
  type GroupInstall,
  type GroupRoom,
} from "./agentGroupsQuery";

export const GROUP_CHATS = "Group chats";
export const GROUPS_LEDE = "The group chats this agent answers in when a message names no agent.";
export const NO_GROUPS =
  "The bot is in no group chat on a channel this agent answers on. Add the bot to a group chat first, and it is offered here.";
export const INSTALL_HERE = "Install in this chat";
export const CHOOSE_A_CHAT = "Choose a group chat";
export const INSTALL_QUESTION = (chat: string): string => `Install this agent in ${chat}?`;
export const REMOVE_QUESTION = (chat: string): string => `Take this agent out of ${chat}?`;
export const WHAT_AN_INSTALL_DOES =
  "Messages in the chat that name no agent are answered by this one. What it may say there is still decided by who is in the chat.";
export const WHAT_A_REMOVAL_DOES = "Messages in the chat that name no agent are no longer answered by this one.";
export const THE_BOT_LEFT = "The bot has left this chat";
export const NOT_CHANGED = "Nothing was changed";

type Pending = { readonly kind: "install"; readonly room: GroupRoom } | { readonly kind: "remove"; readonly install: GroupInstall };

interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

export function AgentGroups({ agentId }: { readonly agentId: string }) {
  const chooserId = useId();
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentGroupsApiPath(agentId), version);
  const shown = useMemo(() => (answer.data === null ? null : readGroups(answer.data)), [answer.data]);
  const [chosen, setChosen] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);

  if (shown === null) {
    return null;
  }

  const room = shown.rooms.find((one) => roomKey(one) === chosen) ?? null;

  const confirm = () => {
    if (pending === null) {
      return;
    }
    const doing = pending;
    setSending(true);
    void (async () => {
      const result =
        doing.kind === "install"
          ? await request<unknown>(agentGroupsApiPath(agentId), {
              method: "POST",
              body: { channel: doing.room.channel, room_ref: doing.room.room_ref },
            })
          : await request<unknown>(agentGroupRemovalApiPath(agentId), {
              method: "POST",
              body: { install_id: doing.install.id },
            });
      setSending(false);
      setPending(null);
      if (result.ok) {
        setChosen("");
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setRefused(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
    })();
  };

  const nothing = shown.installs.length === 0 && shown.rooms.length === 0;
  return (
    <SectionCard title={GROUP_CHATS} lede={GROUPS_LEDE}>
      <div data-slot="agent-groups" className="flex min-w-0 flex-col gap-3">
        {refused === null ? null : (
          <FailureNotice failure={refused.failure} title={NOT_CHANGED} {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })} />
        )}
        {nothing ? <Note>{NO_GROUPS}</Note> : null}
        {shown.installs.length === 0 ? null : (
          <ul aria-label="Group chats this agent is installed in" className="m-0 flex list-none flex-col gap-2 p-0">
            {shown.installs.map((one) => (
              <li key={one.id} className="flex min-w-0 flex-wrap items-center gap-2">
                <MessagesSquare aria-hidden className="size-4 text-dim" />
                <span className="min-w-0 break-words font-medium text-ink">{chatName(one)}</span>
                <Chip>{one.channel}</Chip>
                {one.present ? null : <span className="text-[12px] text-dim">{THE_BOT_LEFT}</span>}
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto min-h-11 sm:min-h-8"
                  aria-label={`Take this agent out of ${chatName(one)}`}
                  disabled={sending}
                  onClick={() => {
                    setRefused(null);
                    setPending({ kind: "remove", install: one });
                  }}
                >
                  Take out
                </Button>
              </li>
            ))}
          </ul>
        )}
        {shown.rooms.length === 0 ? null : (
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={chooserId} className="text-[13px] font-medium text-ink">
                {CHOOSE_A_CHAT}
              </label>
              <NativeSelect id={chooserId} describedBy="" invalid={false} value={chosen} onChange={setChosen}>
                <option value="">{CHOOSE_A_CHAT}</option>
                {shown.rooms.map((one) => (
                  <option key={roomKey(one)} value={roomKey(one)}>
                    {chatName(one)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button
              size="sm"
              className="min-h-11 sm:min-h-8"
              disabled={sending || room === null}
              onClick={() => {
                if (room !== null) {
                  setRefused(null);
                  setPending({ kind: "install", room });
                }
              }}
            >
              {INSTALL_HERE}
            </Button>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={
          pending === null ? "" : pending.kind === "install" ? INSTALL_QUESTION(chatName(pending.room)) : REMOVE_QUESTION(chatName(pending.install))
        }
        consequence={pending?.kind === "remove" ? WHAT_A_REMOVAL_DOES : WHAT_AN_INSTALL_DOES}
        confirmLabel={pending?.kind === "remove" ? "Take it out" : "Install it"}
        cancelLabel="Not now"
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
