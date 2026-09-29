/**
 * Connecting a channel one screen at a time, on the kit's `ConnectFlow`: the vendor's steps with a
 * picture each, this install's events address where a step asks for it, and the channel's own
 * set-up form on the last screen, with its test message once the set-up is saved.
 *
 * **The steps are each channel's own**, declared beside its wire (`GUIDE` in its module under
 * `brain.channels`, read by `brain.channels.adapter.channel_guides`) and served on the channel's
 * row, so this page holds no vendor's words. A channel's last step asks for exactly its record's
 * fields and its secret, which the API holds, and that step draws the Profile's own `SetUp`: the
 * same fields, confirmation and refusals, and a secret typed there goes to the vault once.
 *
 * **Saving does not close the flow.** The page is told only when the flow is closed, because the
 * page reloads the channel when it is told, and a reload would take the flow down with it before
 * the test message it offers next could be sent.
 *
 * **Closing keeps the step, never the secret.** `kit/flowMemory.ts` holds the step per channel for
 * as long as the tab is open, and a saved set-up forgets it.
 *
 * Task ids: M10.5.6, M10.6.3, M27.13.1
 */

import { Copy } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ConnectFlow, copied, FlowDialog, forgetFlow, indexOf, Note, recallFlow, rememberFlow } from "../../components/kit";
import { Button } from "../../components/ui/button";
import type { ChannelRow } from "./channelRows";
import { SAVE_FIRST, SetUp, TestMessage } from "./ChannelProfile";

/** The ask a step names when it shows this install's events address to paste. */
export const EVENTS_ADDRESS_ASK = "events_address";

export const FLOW_DESCRIPTION = "One screen at a time. Close it whenever you need to: it keeps your place, never the secret.";
export const EVENTS_ADDRESS = "This install's events address";
export const COPY_ADDRESS = "Copy the address";
export const ADDRESS_COPIED = "Copied.";
export const ADDRESS_NOT_COPIED = "Your browser did not allow copying. Select the address and copy it yourself.";
export const NO_ADDRESS =
  "This install names no address of its own yet, so there is no events address to paste. Set the install's sign-in redirect address first.";

export function connectLabel(row: ChannelRow): string {
  return `Connect ${row.label}`;
}

/** The memory key a channel's flow keeps its place under. */
export function channelFlowKey(name: string): string {
  return `channel:${name}`;
}

function EventsAddress({ address }: { readonly address: string }) {
  const [said, setSaid] = useState<"done" | "failed" | null>(null);
  if (address === "") {
    return <Note kind="not-yet">{NO_ADDRESS}</Note>;
  }
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <p className="m-0 text-[12.5px] text-dim">{EVENTS_ADDRESS}</p>
      <code className="rounded bg-sunk px-2 py-1.5 text-[12px] [overflow-wrap:anywhere]">{address}</code>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="min-h-11 self-start sm:min-h-8"
        onClick={() => {
          void (async () => {
            setSaid((await copied(address)) ? "done" : "failed");
          })();
        }}
      >
        <Copy aria-hidden />
        {COPY_ADDRESS}
      </Button>
      {said === null ? null : (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {said === "done" ? ADDRESS_COPIED : ADDRESS_NOT_COPIED}
        </p>
      )}
    </div>
  );
}

export function ChannelFlow({
  row,
  onClose,
}: {
  readonly row: ChannelRow;
  /** Told the API's sentence when a set-up was saved in the flow, and null when none was. */
  readonly onClose: (told: string | null) => void;
}) {
  const steps = row.steps;
  const key = channelFlowKey(row.channel);
  const [at, setAt] = useState<string>(() => recallFlow<string>(key) ?? steps[0]?.key ?? "");
  const [told, setTold] = useState<string | null>(null);
  const last = steps[steps.length - 1];
  const panels: Record<string, ReactNode> = {};
  for (const one of steps) {
    if (one.asks.includes(EVENTS_ADDRESS_ASK)) {
      panels[one.key] = <EventsAddress address={row.events_address} />;
    }
  }
  if (last !== undefined) {
    panels[last.key] = (
      <div className="flex min-w-0 flex-col gap-4">
        <SetUp
          row={row}
          onChanged={(sentence) => {
            forgetFlow(key);
            setTold(sentence);
          }}
        />
        {told === null && row.status === "not_set_up" ? <Note>{SAVE_FIRST}</Note> : <TestMessage row={row} />}
      </div>
    );
  }
  return (
    <FlowDialog
      title={connectLabel(row)}
      description={FLOW_DESCRIPTION}
      onClose={() => {
        onClose(told);
      }}
    >
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      <ConnectFlow
        steps={steps}
        at={indexOf(steps, at)}
        onAt={(index) => {
          const next = steps[index];
          if (next !== undefined) {
            setAt(next.key);
            rememberFlow<string>(key, next.key);
          }
        }}
        panels={panels}
      />
    </FlowDialog>
  );
}
