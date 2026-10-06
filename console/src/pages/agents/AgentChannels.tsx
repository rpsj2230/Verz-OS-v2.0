/**
 * Where an agent answers, on its Profile, and the confirmed switch that changes it (M13.7.4).
 *
 * **The card is drawn from `GET /agents/{id}/lifecycle` and from nothing else.** That route opens to
 * the agent's steward and to a holder of either authority over its row, and is the one 404 for
 * anybody else, so a reader it refuses gets no card at all rather than an empty one: a heading over
 * nothing would say there was something here they may not see. The channels shown are the stored
 * list, named by the boxes the route sent, so a channel the product adds is named the day it is
 * declared and the page holds no list of its own.
 *
 * **The switch goes through `kit/ConfirmDialog`**, because unticking a channel ends the agent's
 * answers there for everybody who asks on it, which `tests/destructive-confirmed.test.ts` counts as
 * destructive. The boxes start ticked as the agent stands, and the body sends the channels the card
 * drew as `expected`, so a page that went stale is the route's 409 in its own sentence and nothing
 * is written. Only a reader the route says may switch them is offered the button; the route asks
 * again whatever the page believed.
 *
 * Rejected: a menu item beside Switch off and Archive. Those acts are about the agent as a whole and
 * open to the lifecycle authority only, and a steward who may switch channels and nothing else would
 * have found a menu of refusals with one live item.
 *
 * Each channel it answers on with an adapter is also listed with how an answer is laid out there
 * and whether it can be installed into group chats there, from the lifecycle view's channel rows
 * (M39.2.4.1), which the API computes from the adapters' own declarations.
 *
 * Task ids: M13.7.4, M39.2.4.1
 */

import { Radio } from "lucide-react";
import { useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import {
  agentChannelsApiPath,
  agentLifecycleApiPath,
  channelLabels,
  PROFILE_WORDS,
  channelsBody,
  readLifecycle,
  readNotChanged,
  type AgentLifecycle,
} from "../agentLifecycleQuery";
import { ChannelChoices, WHERE_IT_ANSWERS } from "./ChannelChoices";

export const CHANGE_CHANNELS = "Change where it answers";
export const CHANNELS_LEDE = "The channels people can ask this agent on. Who can find it and what it may reach do not change here.";
export const ANSWERS_NOWHERE = "No channel is switched on, so nobody can ask this agent anything.";
export const CHANNELS_QUESTION = (name: string): string => `Change where ${name} answers?`;
export const CHANNELS_CONSEQUENCE =
  "People can ask it on the channels ticked and on no other. A channel unticked stops its answers there at once, for everybody.";
export const CHANNELS_DONE = "Where it answers was changed";
export const CHANNELS_NOT_CHANGED = "Nothing was changed";
export const SAVE_CHANNELS = "Save";
export const KEEP_CHANNELS = "Not now";
export const HOW_IT_ANSWERS = "How it answers on each channel";
export const GROUP_CHATS_TOO = "It can be installed into group chats there.";

interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

export function AgentChannels({ agentId }: { readonly agentId: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentLifecycleApiPath(agentId), version);
  const shown = useMemo(() => (answer.data === null ? null : readLifecycle(answer.data)), [answer.data]);
  const [editing, setEditing] = useState<AgentLifecycle | null>(null);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);

  if (shown === null) {
    return null;
  }

  const confirm = () => {
    if (editing === null) {
      return;
    }
    const drawn = editing;
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentChannelsApiPath(drawn.agentId), {
        method: "POST",
        body: channelsBody(drawn, chosen),
      });
      setSending(false);
      setEditing(null);
      if (result.ok) {
        setDone(true);
        setVersion((count) => count + 1);
        return;
      }
      const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setRefused(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
    })();
  };

  const labels = channelLabels(shown);
  return (
    <SectionCard
      title={WHERE_IT_ANSWERS}
      lede={CHANNELS_LEDE}
      action={
        shown.mayChangeChannels ? (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={sending}
            onClick={() => {
              setDone(false);
              setRefused(null);
              setChosen(new Set(shown.channels));
              setEditing(shown);
            }}
          >
            {CHANGE_CHANNELS}
          </Button>
        ) : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-2">
        {refused === null ? null : (
          <FailureNotice
            failure={refused.failure}
            title={CHANNELS_NOT_CHANGED}
            {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
          />
        )}
        {done ? <Notice title={CHANNELS_DONE}>{shown.displayName}</Notice> : null}
        {labels.length === 0 ? (
          <Note>{ANSWERS_NOWHERE}</Note>
        ) : (
          <div data-slot="agent-channels" className="flex min-w-0 flex-wrap items-center gap-1.5">
            <Radio aria-hidden className="size-4 text-dim" />
            {labels.map((label) => (
              <Chip key={label}>{label}</Chip>
            ))}
          </div>
        )}
        {shown.channelRows.some((row) => row.enabled) ? (
          <ul aria-label={HOW_IT_ANSWERS} data-slot="agent-channel-rows" className="m-0 flex list-none flex-col gap-1 p-0 text-[13px] text-dim">
            {shown.channelRows
              .filter((row) => row.enabled)
              .map((row) => (
                <li key={row.name} className="[overflow-wrap:anywhere]">
                  {`${row.label}: ${PROFILE_WORDS[row.profile] ?? PROFILE_WORDS["plain"] ?? ""}.`}
                  {row.groupInstallable ? ` ${GROUP_CHATS_TOO}` : ""}
                </li>
              ))}
          </ul>
        ) : null}
      </div>
      <ConfirmDialog
        open={editing !== null}
        question={editing === null ? "" : CHANNELS_QUESTION(editing.displayName)}
        consequence={CHANNELS_CONSEQUENCE}
        details={
          editing === null ? undefined : (
            <ChannelChoices choices={editing.channelChoices} note={editing.channelsNote} chosen={chosen} onChange={setChosen} />
          )
        }
        confirmLabel={SAVE_CHANNELS}
        cancelLabel={KEEP_CHANNELS}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setEditing(null);
        }}
      />
    </SectionCard>
  );
}
