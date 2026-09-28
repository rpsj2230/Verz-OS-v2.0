/**
 * The About view of one channel: how it works, and its history.
 *
 * **How it works is what the product declares, never a guess.** The features and the most
 * sensitive class it may carry are the adapter's declaration; the verbs a person may use through it
 * are `brain.gate.admission.CHANNEL_VERBS`; how a group is answered is `brain.binding_routes.
 * ROOMS_TOLD` for its wire; whether a platform's signature check is written is
 * `brain.ops.inbound_webhooks`' answer on the Webhooks route. All of it arrives from the API, so
 * the day one changes this view changes with it (M27.15.43).
 *
 * **History is what this install recorded**: who last changed the record, by name, and its newest
 * deliveries, what happened and why, never what was said or who sent it. Every change is also in
 * the audit trail, which the view links to rather than repeating.
 *
 * **Identifiers are under Advanced**: the channel's key, the address its vendor posts to, and the
 * id of whoever last changed it.
 *
 * Task ids: M27.15.43, M27.13.1, M10.1.2, M10.1.3, M27.16.1
 */

import { Link } from "react-router-dom";
import { useResource, type Resource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import {
  DIRECTION_WORDS,
  deliveriesApiPath,
  deliveryWords,
  type DeliveriesBody,
  type DeliveryRow,
  type HealthBody,
} from "../channelsQuery";
import { at } from "../operations/parts";
import { VERIFICATION_LABELS, WEBHOOKS_API_PATH, type WebhooksBody } from "../webhooksQuery";
import { changedByWords, type ChannelRow } from "./channelRows";

export const HOW_HEADING = "How it works";
export const HISTORY_HEADING = "History";
export const READING_HOW = "Loading what this channel declares.";
export const READING_DELIVERIES = "Loading this channel's deliveries.";
export const NO_DELIVERIES = "Nothing has crossed this channel yet";
export const NO_DELIVERIES_DESCRIPTION = "A message received or sent, and a request refused, is listed here with what happened.";
export const AUDIT_LINE = "Every change to its record and its bindings is in the audit trail.";
export const WHEN_OFF =
  "Every request its vendor posts is refused and nothing is sent. No other channel changes.";

/** What each verb lets a person do through a channel, in words. */
export const VERB_WORDS: Readonly<Record<string, string>> = Object.freeze({
  read: "Ask and read",
  write: "Change records",
  invoke: "Run tools",
  approve: "Approve",
  admin: "Administer",
});

function sentence(word: string): string {
  const words = word.replaceAll("_", " ");
  return `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

const DELIVERY_COLUMNS: readonly EntityColumn<DeliveryRow>[] = [
  { id: "when", header: "When", hideable: false, cell: (row) => at(row.recorded_at), text: (row) => at(row.recorded_at) },
  {
    id: "direction",
    header: "Direction",
    cell: (row) => DIRECTION_WORDS[row.direction] ?? row.direction,
    text: (row) => DIRECTION_WORDS[row.direction] ?? row.direction,
  },
  { id: "what", header: "What happened", cell: (row) => deliveryWords(row), text: (row) => deliveryWords(row) },
];

function Declared({ health, row }: { readonly health: HealthBody; readonly row: ChannelRow }) {
  const inbound = useResource<WebhooksBody>(WEBHOOKS_API_PATH);
  const check = inbound.data?.inbound.channels.find((one) => one.channel === row.channel);
  return (
    <FactList>
      <Fact label="Received here">{row.receives ? "Yes, at the address its vendor posts to." : "Not by this release yet."}</Fact>
      <Fact label="What it can do">
        {health.features.length === 0 ? (
          "Plain messages only."
        ) : (
          <span className="flex flex-wrap gap-1.5">
            {health.features.map((one) => (
              <Chip key={one}>{sentence(one)}</Chip>
            ))}
          </span>
        )}
      </Fact>
      <Fact label="Most sensitive">{`${sentence(health.max_classification)} information, and nothing above it.`}</Fact>
      <Fact label="Unchecked labels">
        {health.can_carry_label
          ? "It can show a person the label an unchecked answer carries."
          : "It cannot show the label an unchecked answer carries, so it is never sent one."}
      </Fact>
      <Fact label="What a person may do">
        {health.verbs.length === 0 ? (
          "Nothing."
        ) : (
          <span className="flex flex-wrap gap-1.5">
            {health.verbs.map((one) => (
              <Chip key={one}>{VERB_WORDS[one] ?? sentence(one)}</Chip>
            ))}
          </span>
        )}
      </Fact>
      <Fact label="In a group">{health.rooms_told}</Fact>
      <Fact label="When switched off">{WHEN_OFF}</Fact>
      {check === undefined ? null : (
        <Fact label="Signature check">{`${VERIFICATION_LABELS[check.verification]}. ${check.how}`}</Fact>
      )}
    </FactList>
  );
}

function Deliveries({ row, version }: { readonly row: ChannelRow; readonly version: number }) {
  const answer = useResource<DeliveriesBody>(deliveriesApiPath(row.channel), version);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={READING_DELIVERIES} />;
  }
  if (answer.data.deliveries.length === 0) {
    return <EmptyState title={NO_DELIVERIES} description={NO_DELIVERIES_DESCRIPTION} />;
  }
  return (
    <EntityTable
      caption={`Newest deliveries on ${row.label}`}
      columns={DELIVERY_COLUMNS}
      rows={answer.data.deliveries}
      rowId={(one) => `${one.recorded_at}-${one.direction}-${one.outcome}`}
      rowLabel={(one) => at(one.recorded_at)}
      exportName={`${row.channel}-deliveries`}
    />
  );
}

export function ChannelAbout({
  row,
  health,
  version,
}: {
  readonly row: ChannelRow;
  readonly health: Resource<HealthBody>;
  readonly version: number;
}) {
  const who = changedByWords(row);
  return (
    <div data-slot="channel-about" className="flex min-w-0 flex-col gap-4">
      <SectionCard title={HOW_HEADING}>
        {health.failure !== null ? (
          <FailureState failure={health.failure} />
        ) : health.data === null ? (
          <LoadingState label={READING_HOW} />
        ) : (
          <Declared health={health.data} row={row} />
        )}
      </SectionCard>
      <SectionCard
        title={HISTORY_HEADING}
        footer={
          <p className="m-0 text-[12.5px] text-dim">
            {AUDIT_LINE}{" "}
            <Link to="/audit" className="text-acc-text underline-offset-4 hover:underline">
              Open the audit trail
            </Link>
          </p>
        }
      >
        <div className="flex min-w-0 flex-col gap-3">
          <FactList>
            <Fact label="Last changed">
              {row.changed_at === null ? "Never set up." : `${at(row.changed_at)}${who === undefined ? "" : `, by ${who}`}`}
            </Fact>
          </FactList>
          {row.receives ? <Deliveries row={row} version={version} /> : null}
        </div>
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label="Channel key">
            <span className="font-mono text-[12px]">{row.channel}</span>
          </Fact>
          {row.events_path === "" ? null : (
            <Fact label="Events address">
              <span className="font-mono text-[12px]">{row.events_path}</span>
            </Fact>
          )}
          {row.changed_by === null ? null : (
            <Fact label="Last changed by">
              <span className="font-mono text-[12px]">{row.changed_by}</span>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
