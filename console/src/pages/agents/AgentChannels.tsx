/**
 * Where an agent answers, on its Profile: the web page and every chat a run of it could be carried
 * on, each switched on or off, with a switch for whoever holds the department's connector role.
 *
 * **Everything drawn is the route's answer.** The channels listed are the ones
 * `brain.agent_channel_routes` sent this reader, the web page first; whether each is on is the stored
 * switches' word; the switch appears only where the API said the reader may switch; and a refusal is
 * the API's own sentence. An agent switched on nowhere says so in the owner's words, sent by the API.
 *
 * **Every switch is confirmed**, and the dialog says what changes: the agent answers there, or stops,
 * from the next question on, and the switch is on the audit log.
 *
 * Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3, M39.2.4.4
 */

import { useState } from "react";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";

export const LOADING_CHANNELS = "Reading where this agent answers.";

export function agentChannelsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/channels`;
}

/** A channel as a person reads it. A channel nobody here has heard of is drawn as itself. */
export const CHANNEL_WORDS: Readonly<Record<string, string>> = Object.freeze({
  console: "Web page",
  lark: "Lark",
  slack: "Slack",
  teams: "Microsoft Teams",
  email: "Email",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  widget: "Website chat",
  webhook: "Webhook",
  api: "API",
  scheduler: "Scheduled runs",
});

/** How an answer is laid out on a channel, as a person reads it. */
export const PROFILE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  card: "as cards",
  attachment: "with files attached",
  plain: "as text",
});

interface ChannelState {
  readonly channel: string;
  readonly on: boolean;
  readonly profile: string | null;
  readonly groupInstallable: boolean;
}

interface Channels {
  readonly channels: readonly ChannelState[];
  readonly reachable: boolean;
  readonly unreachable: string | null;
  readonly maySwitch: boolean;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

/** The channels read out of a body, or null when the body is not an object at all. */
export function readChannels(payload: unknown): Channels | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const rows = (Array.isArray(fields["channels"]) ? (fields["channels"] as readonly unknown[]) : [])
    .map(fieldsOf)
    .filter((one): one is Fields => one !== null && typeof one["channel"] === "string")
    .map((one) => ({
      channel: String(one["channel"]),
      on: one["on"] === true,
      profile: typeof one["profile"] === "string" ? one["profile"] : null,
      groupInstallable: one["group_installable"] === true,
    }));
  return {
    channels: rows,
    reachable: fields["reachable"] === true,
    unreachable: typeof fields["unreachable"] === "string" ? fields["unreachable"] : null,
    maySwitch: fields["may_switch"] === true,
  };
}

function wordsFor(channel: string): string {
  return CHANNEL_WORDS[channel] ?? channel;
}

interface Asked {
  readonly channel: string;
  readonly on: boolean;
}

export function AgentChannels({ agentId }: { readonly agentId: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentChannelsApiPath(agentId), version);
  const [asking, setAsking] = useState<Asked | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const channels = answer.data === null ? null : readChannels(answer.data);
  if (answer.busy || channels === null) {
    return <LoadingState label={LOADING_CHANNELS} />;
  }

  const decide = async (one: Asked): Promise<void> => {
    setBusy(true);
    const result = await request<unknown>(agentChannelsApiPath(agentId), { method: "POST", body: one });
    setBusy(false);
    setAsking(null);
    setSaid(result.ok ? null : result.failure.message);
    setVersion((count) => count + 1);
  };

  return (
    <div data-slot="agent-channels" className="flex min-w-0 flex-col gap-2 text-[12.5px]">
      {said === null ? null : (
        <p role="alert" className="m-0 text-crit">
          {said}
        </p>
      )}
      {channels.reachable || channels.unreachable === null ? null : <Note>{channels.unreachable}</Note>}
      <ul data-slot="channels-listed" className="m-0 flex list-none flex-col p-0">
        {channels.channels.map((one) => (
          <li key={one.channel} data-channel={one.channel} className="flex flex-wrap items-center gap-2 border-b border-line py-1.5 last:border-b-0">
            <span className="min-w-0 text-ink [overflow-wrap:anywhere]">
              {wordsFor(one.channel)}
              {one.profile === null ? null : <span className="text-dim">{` ${PROFILE_WORDS[one.profile] ?? one.profile}`}</span>}
            </span>
            <span className="text-dim">{one.on ? "Switched on" : "Switched off"}</span>
            {channels.maySwitch ? (
              <Button className="ml-auto" variant="ghost" size="xs" onClick={() => setAsking({ channel: one.channel, on: !one.on })}>
                {one.on ? "Switch off" : "Switch on"}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={asking !== null}
        question={asking === null ? "" : `Switch ${asking.on ? "on" : "off"} ${wordsFor(asking.channel)} for this agent?`}
        consequence={
          asking?.on === false
            ? "It stops answering there from the next question on, and a question naming it there is answered as if it did not exist. The change is on the audit log."
            : "It answers there from the next question on, to each person who may use it, within what each of them may reach. The change is on the audit log."
        }
        confirmLabel={asking?.on === false ? "Switch off" : "Switch on"}
        cancelLabel="Leave it"
        danger={asking?.on === false}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            void decide(asking);
          }
        }}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
