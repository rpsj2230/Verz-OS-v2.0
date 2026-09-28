/**
 * Channels: each chat surface this install runs, and a person's own chats in My workspace.
 *
 * The administrator's page is one card per channel they may manage, in the API's order: the
 * identifiers the channel was set up with, where its vendor posts, whether its secret is held
 * (never the secret), the switch, what its adapter declares it can do and the most sensitive
 * class it may carry, its health read from its deliveries, the people bound on it, and its newest
 * deliveries. Below them, the set-up form and a test message. `brain.channel_routes` and
 * `brain.binding_routes` answer; `brain.console.channel_health` decides the health; nothing on
 * this page decides who may see a channel, which is the channel's own authority on the server.
 *
 * **Every change is confirmed, and says what it does.** Switching a channel, saving its set-up and
 * unbinding somebody each open a confirmation naming the channel and the consequence, and each is
 * recorded in the audit ledger by the database. A test message is one product sentence to one
 * destination, sent once per record and destination, so it is not.
 *
 * **The person's half is `components/MyChannels.tsx`**, drawn in My workspace, which is where
 * `docs/screens.html` SCREEN 12 puts Channels, under Me.
 *
 * Imported statically: it mounts no heavy library and no stylesheet of its own.
 *
 * Task ids: M10.3.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { SecretField, useSecret } from "../components/ui/secret-field";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./artifactsQuery";
import {
  BOUND_FILTERS,
  BOUND_SORTS,
  CHANNELS_API_PATH,
  TEST_OUTCOMES,
  bindingsApiPath,
  channelApiPath,
  declaredWords,
  deliveriesApiPath,
  deliveryWords,
  healthApiPath,
  healthWord,
  secretWords,
  setupBody,
  setupProblems,
  switchApiPath,
  testApiPath,
  testProblems,
  unbindApiPath,
  type BoundRow,
  type ChannelRow,
  type ChannelsBody,
  type DeliveriesBody,
  type HealthBody,
  type TestBody,
  type UnboundBody,
} from "./channelsQuery";

export const CHANNELS_HEADING = "Channels";
export const CHANNELS_CRUMB = "Govern › Channels";
export const CHANNELS_LEDE =
  "Each chat channel you manage on this install: how it was set up, whether its secret is held, " +
  "whether it is switched on, what it may carry, how it is doing and who is bound on it.";

export const READING_CHANNELS = "Reading the channels you manage.";
export const NO_CHANNELS = "There are no channels you manage on this install.";
export const READING_HEALTH = "Reading how this channel is doing.";
export const READING_BOUND = "Reading who is bound on this channel.";
export const NOBODY_BOUND = "Nobody is bound on this channel.";
export const MORE_BOUND = "This list came back full, so more people are bound than it shows.";
export const READING_DELIVERIES = "Reading this channel's deliveries.";
export const NO_DELIVERIES = "Nothing has been received or sent on this channel yet.";
export const NOT_RECEIVED =
  "This release cannot receive or reply on this channel yet, so it cannot be set up here.";

export const SWITCH_OFF_CONSEQUENCE =
  "It stops receiving and sending at once, and no other channel changes. The switch is recorded " +
  "in the audit ledger with your name.";
export const SWITCH_ON_CONSEQUENCE =
  "It starts receiving at its events address and replying through its vendor. The switch is " +
  "recorded in the audit ledger with your name.";
export const SAVE_CONSEQUENCE =
  "The identifiers below replace the ones kept, and a secret typed here replaces the one in the " +
  "vault. Both are recorded in the audit ledger, never the secret itself.";
export const UNBIND_CONSEQUENCE =
  "The Brain stops answering their chat account as them, at once. They can connect it again with " +
  "a new code. The unbinding is recorded in the audit ledger with your name.";

export const KEEP_LABEL = "Keep it as it is";
export const SAVE_LABEL = "Save set-up";
export const TEST_LABEL = "Send a test message";
export const TEST_TO_LABEL = "Send it to";
export const SECRET_LABEL = "Secret (write only)";
export const ENABLED_LABEL = "Switched on";

/** A failure, kept beside the control that met it. */
type Met = ApiFailure | null;

function Problems({ problems }: { readonly problems: readonly string[] }) {
  return problems.length === 0 ? null : (
    <ul className="form__problems" role="status">
      {problems.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

function Health({ name, version }: { readonly name: string; readonly version: number }) {
  const answer = useResource<HealthBody>(healthApiPath(name), version);
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.data === null) {
    return (
      <p className="note" role="status">
        {READING_HEALTH}
      </p>
    );
  }
  const health = answer.data;
  const fault = health.last_fault;
  return (
    <>
      <p>
        <Chip label={healthWord(health.health)} /> {health.told}
      </p>
      <dl className="fields" aria-label={`How ${name} is doing`}>
        <div className="fields__row">
          <dt>Last received</dt>
          <dd>{health.last_received_at === null ? "Nothing received yet." : when(health.last_received_at)}</dd>
        </div>
        <div className="fields__row">
          <dt>Last sent</dt>
          <dd>{health.last_sent_at === null ? "Nothing sent yet." : when(health.last_sent_at)}</dd>
        </div>
        <div className="fields__row">
          <dt>Last fault</dt>
          <dd>{fault === null ? "No fault recorded." : `${deliveryWords(fault)}, ${when(fault.recorded_at)}`}</dd>
        </div>
        <div className="fields__row">
          <dt>What it may carry</dt>
          <dd>{declaredWords(health)}</dd>
        </div>
      </dl>
    </>
  );
}

function Bound({
  name,
  version,
  onChanged,
}: {
  readonly name: string;
  readonly version: number;
  readonly onChanged: () => void;
}) {
  const listing = useListing<BoundRow>(bindingsApiPath(name), { choices: BOUND_FILTERS, version });
  const [confirming, setConfirming] = useState<BoundRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Met>(null);

  const unbind = useCallback(
    (row: BoundRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<UnboundBody>(unbindApiPath(name), {
          method: "POST",
          body: { principal_id: row.principal_id },
        });
        setBusy(false);
        setConfirming(null);
        if (result.ok) {
          onChanged();
          return;
        }
        setFailure(result.failure);
      })();
    },
    [name, onChanged],
  );

  const body = listing.body as { truncated?: unknown; told?: unknown } | null;
  return (
    <>
      <h3>Bound people</h3>
      <ListControls label={`Find a person bound on ${name}`} listing={listing} choices={BOUND_FILTERS} sorts={BOUND_SORTS} />
      {failure === null ? null : <FailureNotice failure={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question={`Unbind ${confirming.display_name} from ${name}?`}
          consequence={UNBIND_CONSEQUENCE}
          confirmLabel="Unbind"
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            unbind(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}
      {listing.failure ? (
        <FailureNotice failure={listing.failure} />
      ) : listing.busy ? (
        <p className="note" role="status">
          {READING_BOUND}
        </p>
      ) : listing.rows.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NOTHING_MATCHES : NOBODY_BOUND}</p>
      ) : (
        <>
          <ul aria-label={`People bound on ${name}`}>
            {listing.rows.map((row) => (
              <li key={row.principal_id}>
                {row.display_name} <code>{row.principal_id}</code>, since {when(row.bound_at)}{" "}
                <button
                  type="button"
                  className="button"
                  aria-label={`Unbind: ${row.display_name}`}
                  disabled={busy}
                  onClick={() => {
                    setFailure(null);
                    setConfirming(row);
                  }}
                >
                  Unbind
                </button>
              </li>
            ))}
          </ul>
          <ShowMore listing={listing} />
        </>
      )}
      {body?.truncated === true ? <p className="note">{MORE_BOUND}</p> : null}
      {typeof body?.told === "string" ? <p className="hint note">{body.told}</p> : null}
    </>
  );
}

function Deliveries({ name, version }: { readonly name: string; readonly version: number }) {
  const answer = useResource<DeliveriesBody>(deliveriesApiPath(name), version);
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.data === null) {
    return (
      <p className="note" role="status">
        {READING_DELIVERIES}
      </p>
    );
  }
  if (answer.data.deliveries.length === 0) {
    return <p className="note">{NO_DELIVERIES}</p>;
  }
  return (
    <ul aria-label={`Newest deliveries on ${name}`}>
      {answer.data.deliveries.slice(0, 10).map((row, index) => (
        <li key={`${row.recorded_at}-${String(index)}`}>
          {when(row.recorded_at)}: {deliveryWords(row)}
        </li>
      ))}
    </ul>
  );
}

function SetUp({ row, onChanged }: { readonly row: ChannelRow; readonly onChanged: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({ ...row.tenant });
  const secret = useSecret();
  const [enabled, setEnabled] = useState(row.enabled);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Met>(null);

  const submit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const found = setupProblems(row.tenant_fields, values);
      setProblems(found);
      setFailure(null);
      setConfirming(found.length === 0);
    },
    [row.tenant_fields, values],
  );

  const save = useCallback(() => {
    // Read from the field only now, and the field emptied in the same call: the secret is sent
    // once and kept nowhere here. See `A_SECRET_IS_WRITTEN_ONCE_AND_NEVER_READ_BACK`.
    const body = setupBody(enabled, row.tenant_fields, values, secret.take());
    setBusy(true);
    void (async () => {
      const result = await request<ChannelRow>(channelApiPath(row.channel), { method: "PUT", body });
      setBusy(false);
      setConfirming(false);
      if (result.ok) {
        onChanged();
        return;
      }
      setFailure(result.failure);
    })();
  }, [enabled, row.channel, row.tenant_fields, values, secret, onChanged]);

  const label = `Set up ${row.channel}`;
  return (
    <>
      <form className="form" aria-label={label} onSubmit={submit}>
        {row.tenant_fields.map((field) => (
          <label className="control-label" key={field}>
            {field}{" "}
            <input
              className="form-control"
              type="text"
              name={field}
              autoComplete="off"
              spellCheck={false}
              value={values[field] ?? ""}
              onChange={(event) => {
                setValues({ ...values, [field]: event.target.value });
              }}
            />
          </label>
        ))}
        <SecretField
          secret={secret}
          label={SECRET_LABEL}
          stored={row.secret_held === true}
          disabled={busy}
        />
        <label className="control-label">
          <input
            type="checkbox"
            name="enabled"
            checked={enabled}
            onChange={(event) => {
              setEnabled(event.target.checked);
            }}
          />{" "}
          {ENABLED_LABEL}
        </label>
        <Problems problems={problems} />
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {SAVE_LABEL}
          </button>
        </div>
      </form>
      {confirming ? (
        <ConfirmAction
          question={`Save the set-up of ${row.channel}?`}
          consequence={SAVE_CONSEQUENCE}
          confirmLabel={SAVE_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={save}
          onCancel={() => {
            setConfirming(false);
          }}
        />
      ) : null}
      {failure === null ? null : <FailureNotice failure={failure} fields={[...row.tenant_fields, "secret"]} />}
    </>
  );
}

function TestMessage({ name, onChanged }: { readonly name: string; readonly onChanged: () => void }) {
  const [to, setTo] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Met>(null);

  const submit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const found = testProblems(to);
      setProblems(found);
      setFailure(null);
      setSaid(null);
      if (found.length > 0) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<TestBody>(testApiPath(name), { method: "POST", body: { to: to.trim() } });
        setBusy(false);
        if (result.ok) {
          setSaid(`${TEST_OUTCOMES[result.data.outcome] ?? result.data.outcome} ${result.data.told}`);
          onChanged();
          return;
        }
        setFailure(result.failure);
      })();
    },
    [name, to, onChanged],
  );

  return (
    <form className="form" aria-label={`${TEST_LABEL} on ${name}`} onSubmit={submit}>
      <label className="control-label">
        {TEST_TO_LABEL}{" "}
        <input
          className="form-control"
          type="text"
          name="to"
          autoComplete="off"
          spellCheck={false}
          value={to}
          onChange={(event) => {
            setTo(event.target.value);
          }}
        />
      </label>
      <Problems problems={problems} />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {TEST_LABEL}
        </button>
      </div>
      {said === null ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} fields={["to"]} />}
    </form>
  );
}

function ChannelCard({ row, onChanged }: { readonly row: ChannelRow; readonly onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Met>(null);
  const changed = useCallback(() => {
    setVersion((current) => current + 1);
    onChanged();
  }, [onChanged]);

  const flip = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<ChannelRow>(switchApiPath(row.channel), {
        method: "POST",
        body: { enabled: !row.enabled },
      });
      setBusy(false);
      setConfirming(false);
      if (result.ok) {
        changed();
        return;
      }
      setFailure(result.failure);
    })();
  }, [row.channel, row.enabled, changed]);

  const verb = row.enabled ? "Switch off" : "Switch on";
  const tenant = Object.entries(row.tenant);
  return (
    <section className="card" aria-label={row.channel}>
      <h2>
        {row.channel} <Chip label={row.configured ? (row.enabled ? "On" : "Off") : "Not set up"} />
      </h2>
      <dl className="fields" aria-label={`How ${row.channel} is set up`}>
        <div className="fields__row">
          <dt>Receives here</dt>
          <dd>{row.receives ? row.events_path : NOT_RECEIVED}</dd>
        </div>
        <div className="fields__row">
          <dt>Identifiers</dt>
          <dd>
            {tenant.length === 0
              ? "None kept."
              : tenant.map(([key, value]) => (
                  <span key={key}>
                    {key}: <code>{value}</code>{" "}
                  </span>
                ))}
          </dd>
        </div>
        <div className="fields__row">
          <dt>Secret</dt>
          <dd>{row.configured ? secretWords(row.secret_held) : "Not set up, so no secret is kept."}</dd>
        </div>
        <div className="fields__row">
          <dt>Last changed</dt>
          <dd>
            {row.updated_at === null ? "Never." : `${when(row.updated_at)}, by ${row.updated_by ?? "nobody named"}`}
          </dd>
        </div>
      </dl>
      {row.configured ? (
        <div className="form-actions">
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => {
              setFailure(null);
              setConfirming(true);
            }}
          >
            {verb}
          </button>
        </div>
      ) : null}
      {confirming ? (
        <ConfirmAction
          question={`${verb} ${row.channel}?`}
          consequence={row.enabled ? SWITCH_OFF_CONSEQUENCE : SWITCH_ON_CONSEQUENCE}
          confirmLabel={verb}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={flip}
          onCancel={() => {
            setConfirming(false);
          }}
        />
      ) : null}
      {failure === null ? null : <FailureNotice failure={failure} />}
      <h3>How it is doing</h3>
      <Health name={row.channel} version={version} />
      {row.receives ? (
        <>
          <Bound name={row.channel} version={version} onChanged={changed} />
          <h3>Newest deliveries</h3>
          <Deliveries name={row.channel} version={version} />
          <h3>Set up</h3>
          <SetUp row={row} onChanged={changed} />
          <h3>Test</h3>
          <TestMessage name={row.channel} onChanged={changed} />
        </>
      ) : null}
    </section>
  );
}

export function Channels() {
  const [version, setVersion] = useState(0);
  const answer = useResource<ChannelsBody>(CHANNELS_API_PATH, version);
  const changed = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{CHANNELS_CRUMB}</p>
      <h1>{CHANNELS_HEADING}</h1>
      <p className="lede">{CHANNELS_LEDE}</p>
      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure} />
        </section>
      ) : answer.data === null ? (
        <p className="note" role="status">
          {READING_CHANNELS}
        </p>
      ) : answer.data.channels.length === 0 ? (
        <p className="note">{NO_CHANNELS}</p>
      ) : (
        <>
          {answer.data.channels.map((row) => (
            <ChannelCard key={row.channel} row={row} onChanged={changed} />
          ))}
          <p className="hint note">{answer.data.told}</p>
        </>
      )}
    </article>
  );
}
