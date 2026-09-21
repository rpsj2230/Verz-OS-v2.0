/**
 * Staff sources: where this install reads its people from, what that still needs, and a trial
 * run that reads the source and changes nothing.
 *
 * It sits under Govern, beside People and grants, which is where `docs/screens.html` puts
 * everything about who is here and what they may reach. That file draws thirteen screens and
 * this is not one of them, so the information architecture is followed and the layout is taken
 * from the nearest neighbours it does draw: Connectors is a list of outside systems with a
 * state beside each, and People and grants is a listing with one thing opened next to it.
 *
 * **Three questions, in the order somebody asks them.** Which list is this install set to read;
 * what else it could have been set to and what each of those would need; and what would happen
 * if it ran. The middle one is a listing and the other two are panels, which is the shape every
 * Govern screen in the design has.
 *
 * **Nothing here decides anything.** `brain.console.staff_source_view` decides which sources a
 * reader is shown, what the chosen one is, whether the trial is reachable and what a run would
 * change, and `brain.staff_source_routes` serves that. A reader who reaches no source is
 * answered an empty page, which is what an install with nothing to show answers, and this page
 * draws both identically because there is no field that tells them apart.
 *
 * **The trial is a button and not a load.** See
 * `staffSourcesQuery.A_TRIAL_IS_A_REQUEST_SOMEBODY_MAKES`: it is an outbound call to a client's
 * own directory and a wider disclosure than the rest of the screen, so nothing is asked until
 * somebody asks for it.
 *
 * **A source is chosen and connected here since 2026-09-21.** `components/ConnectStaffSource.tsx`
 * draws the API's steps for each kind of source, tests it, saves it and runs its first sync. See
 * `staffSourcesQuery.A_SOURCE_IS_CONNECTED_FROM_THIS_SCREEN`.
 *
 * **No listing on it carries a figure**, which is the one convention of the design this screen
 * cannot keep. See `staffSourcesQuery.THE_DESIGN_COUNTS_AND_THIS_SCREEN_CANNOT`. The one number a
 * person can make it draw is how many people a connection test read from their own directory,
 * which is an answer to the credential they typed and not a listing narrowed by anybody's grant.
 *
 * **No tone is computed from a value.** `ui/Status.tsx` is the only module allowed to turn a
 * payload into a colour and its vocabulary is the four connector health words, none of which a
 * staff source has. So a source's state is the API's own sentence and a chosen source is marked
 * with a badge whose tone is written at the call site, which is `ui/Badge.tsx`'s rule.
 *
 * Imported statically rather than split, for `Scopes`' reason: neither heavy library and no
 * stylesheet of its own.
 *
 * **Since 2026-09-21 it also shows what the nightly sync did, keeps its credential and hands on a
 * leaver's agents.** The runs are rows the worker wrote, read with the page; the credential card
 * is drawn only for a reader the API answers, with a replace that is confirmed first; and the
 * agents whose owner a run marked as having left are listed with a take-on that is confirmed too.
 * None of the three applies a plan: the worker does.
 *
 * M27.7.2 is this screen: a staff source is chosen, configured and tried here before it runs.
 * A leaver's agents are listed stopped, and taking one on starts it again (M1.8.9, M26.3.2).
 *
 * Task ids: M1.6.12, M1.8.6, M1.8.9, M27.7.2
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Badge } from "../ui/Badge";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import {
  readCredential,
  readRuns,
  readStaffSources,
  readTransfers,
  readTrial,
  transferApiPath,
  wasRead,
  CREDENTIAL_API_PATH,
  CREDENTIAL_BLANK,
  RUNS_API_PATH,
  STAFF_SOURCES_API_PATH,
  TRANSFERS_API_PATH,
  TRIAL_API_PATH,
  type Read,
  type SourceOption,
  type Transfer,
  type TrialAnswer,
  type TrialRun,
} from "./staffSourcesQuery";
import { ConfirmAction } from "../components/ConfirmAction";
import { ConnectStaffSource } from "../components/ConnectStaffSource";
import { FailureNotice } from "../ui/FailureNotice";

export const STAFF_SOURCES_HEADING = "Staff sources";

/** Under the heading. Says what a staff source is, in the vocabulary the settings use. */
export const STAFF_SOURCES_LEDE =
  "Where this install reads the list of who works here: a spreadsheet, Google Workspace, " +
  "Microsoft, Lark or a directory. A staff list says who exists and which department they are " +
  "in; it does not sign anybody in, and what it is believed about is set here and not in it.";

/** An empty listing, whichever of the reasons it is empty. */
export const NO_SOURCES = "There are no staff sources to show.";

/** The heading over the source this install is set to read. */
export const WHAT_THIS_INSTALL_READS = "What this install reads";

/** The heading over everything it could have been set to. */
export const WHAT_IT_COULD_READ = "What it could read";

/** The heading over where the choice is actually made. */
export const WHERE_THE_CHOICE_IS_MADE = "Choosing a source";

/** The heading over the trial. */
export const TRY_IT_BEFORE_IT_RUNS = "Try it before it runs";

/** The heading over a trial that could not be run at all. */
export const NOTHING_TRIED = "Nothing here has tried your staff source";

/** The heading over a trial the source itself refused. */
export const THE_SOURCE_REFUSED = "That source could not be read";

/** What the button says. A verb, so it says what pressing it does. */
export const RUN_THE_TRIAL = "Run a trial";

/** What the button says while the request is out. */
export const RUNNING_THE_TRIAL = "Reading the source.";

/** Said beside a source this install is set to read. Its tone is a literal; see `ui/Badge.tsx`. */
export const CHOSEN = "chosen";

/** Said beside the one option that reads no list at all. */
export const READS_NO_LIST = "This option reads no staff list at all.";

/** What a source still needs before it can be read, in words rather than as a count. */
export const STILL_TO_SET = "Still to set";

/** What a source needs at all, whether or not this install has set it. */
export const NEEDS = "Settings this source needs";

/** Said over a plan that would change nothing. */
export const CHANGES_NOTHING = "A run would change nothing.";

/** The accessible names of the lists on this page. */
export const SOURCES_LIST_LABEL = "Staff sources this install could read";
export const WOULD_ADD_LABEL = "People a run would add";
export const ABSENT_LABEL = "People the source did not mention";
export const WOULD_REMOVE_LABEL = "People a run would remove";
export const WOULD_DEACTIVATE_LABEL = "People the source says have left";
export const WITHHELD_LABEL = "Why fewer people would be removed than are missing";
export const REFUSALS_LABEL = "What this run refuses to act on";
export const GAPS_LABEL = "What is wrong with this source";
export const ROLE_GRANTS_TO_ADD_LABEL = "Role assertions a run would add";
export const ROLE_GRANTS_TO_REMOVE_LABEL = "Role assertions a run would remove";

/** One list of plain strings, drawn only when there is something in it. */
function Lines({ label, lines }: { readonly label: string; readonly lines: readonly string[] }) {
  if (lines.length === 0) {
    // Nothing, and deliberately not a sentence. An empty list on a plan means the run would do
    // none of that, and a heading with "none" under it is a shape where a fact would be.
    return null;
  }
  return (
    <>
      <h3>{label}</h3>
      <ul className="roster" aria-label={label}>
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </>
  );
}

/** One option: what it is, what it means, and what this install has not set for it. */
function Option({ option }: { readonly option: SourceOption }) {
  return (
    <li>
      <h3>
        <code>{option.name}</code> {option.chosen ? <Badge label={CHOSEN} tone="positive" /> : null}
      </h3>
      <p>{option.meaning}</p>
      {option.reads_a_list ? null : <p className="note">{READS_NO_LIST}</p>}
      {/*
       * The names of settings and never what they are set to.
       * `brain.console.staff_source_view.A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_
       * CREDENTIAL` is the argument, and the shape that keeps it is that the API sends names:
       * there is no value on this payload to render, here or anywhere below.
       */}
      {option.needs.length === 0 ? null : (
        <dl className="fields" aria-label={`${NEEDS}: ${option.name}`}>
          <div className="fields__row">
            <dt>{NEEDS}</dt>
            <dd>
              {option.needs.map((name) => (
                <Chip key={name} label={name} />
              ))}
            </dd>
          </div>
          {option.unsupplied.length === 0 ? null : (
            <div className="fields__row">
              <dt>{STILL_TO_SET}</dt>
              <dd>
                {option.unsupplied.map((name) => (
                  <Chip key={name} label={name} />
                ))}
              </dd>
            </div>
          )}
        </dl>
      )}
    </li>
  );
}

/** One plan, drawn as lists of things and never as counts of them. */
function Plan({ run }: { readonly run: TrialRun }) {
  if (run.plan === null || run.plan === undefined) {
    return (
      <Notice title={THE_SOURCE_REFUSED}>
        <ul>
          {run.refusals.map((why) => (
            <li key={why}>{why}</li>
          ))}
        </ul>
      </Notice>
    );
  }
  const plan = run.plan;
  return (
    <>
      <p>
        <Chip label={plan.source} />
      </p>
      {plan.changes_nothing ? <p className="note">{CHANGES_NOTHING}</p> : null}
      <Lines label={REFUSALS_LABEL} lines={plan.refusals} />
      <Lines label={GAPS_LABEL} lines={plan.gaps} />
      {plan.would_add.length === 0 ? null : (
        <>
          <h3>{WOULD_ADD_LABEL}</h3>
          <ul className="roster" aria-label={WOULD_ADD_LABEL}>
            {plan.would_add.map((person) => (
              <li key={person.work_address}>
                {person.display_name} <code>{person.work_address}</code>
                {person.department === "" ? null : <Chip label={person.department} />}
                {person.groups.map((group) => (
                  <Chip key={group} label={group} />
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
      <Lines label={ABSENT_LABEL} lines={plan.absent} />
      <Lines label={WOULD_REMOVE_LABEL} lines={plan.would_remove} />
      <Lines label={WITHHELD_LABEL} lines={plan.withheld} />
      <Lines label={WOULD_DEACTIVATE_LABEL} lines={plan.would_deactivate} />
      <Lines
        label={ROLE_GRANTS_TO_ADD_LABEL}
        lines={plan.role_grants_to_add.map(
          (one) => `${one.principal_id}: ${one.role} from ${one.source_group}`,
        )}
      />
      <Lines
        label={ROLE_GRANTS_TO_REMOVE_LABEL}
        lines={plan.role_grants_to_remove.map(
          (one) => `${one.principal_id}: ${one.role} from ${one.source_group}`,
        )}
      />
    </>
  );
}

/**
 * The trial, asked for when somebody presses the button and never before.
 *
 * There is no control anywhere on this page that applies what a trial proposes, and that is not
 * an omission to be filled in later: applying one provisions people and writes role assertions,
 * which is a different authority, and `brain.staff_source_routes` has no verb that could.
 */
function Trial() {
  const [read, setRead] = useState<Read<TrialRun> | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<TrialAnswer>(TRIAL_API_PATH);
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setRead(readTrial(result.data));
    })();
  }, []);

  return (
    <>
      <button type="button" className="button" disabled={busy} onClick={run}>
        {RUN_THE_TRIAL}
      </button>
      {busy ? (
        <p className="note" role="status">
          {RUNNING_THE_TRIAL}
        </p>
      ) : null}
      {failure === null ? null : (
        <FailureNotice failure={failure} />
      )}
      {read === null ? null : wasRead(read) ? (
        <Plan run={read.panel} />
      ) : (
        <Notice title={NOTHING_TRIED}>
          <p>{read.unread}</p>
        </Notice>
      )}
    </>
  );
}

// ============================================================ what the nightly sync did
/** The heading over the scheduled runs. */
export const NIGHTLY_SYNC = "What the nightly sync did";

/** Said when there is no run to show, whichever of the reasons it is. */
export const NO_RUNS = "No nightly run has been recorded.";

/** Said beside a run that wrote no member. The API sets the flag; this only words it. */
export const CHANGED_NOBODY = "Nobody was changed by this run.";

/** The accessible names of a run's lists. */
export const RUN_ADDED_LABEL = "People this run added";
export const RUN_MARKED_LEFT_LABEL = "People this run marked as having left";
export const RUN_RENAMED_LABEL = "People whose address moved";
export const RUN_WITHHELD_LABEL = "What this run held back";

/** The heading over the credential the sync reads with. */
export const SYNC_CREDENTIAL = "The credential the nightly sync reads with";

/** Said when the vault holds one, and when it does not. */
export const CREDENTIAL_HELD = "A credential is held in the vault.";
export const CREDENTIAL_NOT_HELD = "No credential is held, so the nightly sync cannot read the staff list.";

/** What the replace button and its confirmation say. */
export const REPLACE_CREDENTIAL = "Replace credential";
export const KEEP_CREDENTIAL = "Keep the current one";
export const REPLACE_QUESTION = "Replace the credential the nightly sync reads the staff list with?";
export const REPLACE_CONSEQUENCE =
  "The next nightly run reads with the new one. If the source refuses it, that run changes " +
  "nobody and says so here. The value is never shown again.";

/** The heading over a leaver's agents. */
export const WAITING_FOR_AN_OWNER = "Agents waiting for a new owner";

/** Said when there is nothing to take on, whichever of the reasons it is. */
export const NO_TRANSFERS = "No agent is waiting for a new owner that you may take on.";

/** Said about every agent listed: stopped until somebody takes it on, and never widened. */
export const STOPPED_UNTIL_TAKEN =
  "Each is stopped until somebody takes it on. Taking one on makes you its owner and starts it " +
  "again, and changes nothing it can reach.";

/** The take-on button and its confirmation. */
export const TAKE_ON = "Take on";
export const KEEP_WAITING = "Leave it waiting";
export const TAKE_ON_CONSEQUENCE =
  "You become the person who answers for it and it starts running again. Its ceiling does not " +
  "change, so it reaches nothing it could not reach before. The change of owner is recorded in " +
  "the audit ledger.";

/** The scheduled runs, loaded with the page. See `A_RUN_IS_A_RECORD_AND_NOT_A_CALL`. */
function NightlySync({ version }: { readonly version: number }) {
  const answer = useResource<unknown>(RUNS_API_PATH, version);
  const runs = readRuns(answer.data);
  if (answer.failure !== null) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return null;
  }
  if (runs.length === 0) {
    return <p className="note">{NO_RUNS}</p>;
  }
  return (
    <ul className="roster" aria-label={NIGHTLY_SYNC}>
      {runs.map((run) => (
        <li key={`${run.source}-${run.finished_at}`}>
          <p>
            <Chip label={run.source} /> <Chip label={run.outcome} /> <time>{run.finished_at}</time>
          </p>
          <p>{run.detail}</p>
          {run.changed_nobody ? <p className="note">{CHANGED_NOBODY}</p> : null}
          <Lines label={RUN_ADDED_LABEL} lines={run.added} />
          <Lines label={RUN_MARKED_LEFT_LABEL} lines={run.marked_left} />
          <Lines label={RUN_RENAMED_LABEL} lines={run.renamed} />
          <Lines label={RUN_WITHHELD_LABEL} lines={run.withheld} />
        </li>
      ))}
    </ul>
  );
}

/**
 * The credential card, drawn only for a reader the API answers.
 *
 * A reader without the credential authority over everything is answered a 404, which is also
 * every other absence, so the card is left out rather than drawn as a failure: a failure notice
 * here would tell a reader that a credential screen exists and they may not see it.
 */
function SyncCredential() {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(CREDENTIAL_API_PATH, version);
  const held = readCredential(answer.data);
  const [value, setValue] = useState("");
  const [blank, setBlank] = useState(false);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [told, setTold] = useState("");
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const send = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(CREDENTIAL_API_PATH, { method: "PUT", body: { value } });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setValue("");
      setTold(readCredential(result.data)?.told ?? "");
      setVersion((one) => one + 1);
    })();
  }, [value]);

  if (held === null) {
    return null;
  }
  return (
    <section className="card">
      <h2>{SYNC_CREDENTIAL}</h2>
      <p>{held.held === true ? CREDENTIAL_HELD : held.held === false ? CREDENTIAL_NOT_HELD : held.told}</p>
      {held.set_at === null || held.set_at === undefined ? null : (
        <p className="note">
          Written <time>{held.set_at}</time>
        </p>
      )}
      <p className="field-description">{held.form}</p>
      {told === "" ? null : <p className="note">{told}</p>}
      {failure === null ? null : <FailureNotice failure={failure} />}
      <form
        className="form"
        aria-label={REPLACE_CREDENTIAL}
        onSubmit={(event) => {
          event.preventDefault();
          setFailure(null);
          // A blank value is said beside the field before anything is confirmed or sent.
          const empty = value.trim() === "";
          setBlank(empty);
          if (!empty) {
            setPending(true);
          }
        }}
      >
        <label className="control-label">
          New credential{" "}
          <input
            className="form-control"
            type="text"
            name="credential"
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
            }}
          />
        </label>
        {blank ? <p className="field-problem">{CREDENTIAL_BLANK}</p> : null}
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {REPLACE_CREDENTIAL}
          </button>
        </div>
      </form>
      {pending ? (
        <ConfirmAction
          question={REPLACE_QUESTION}
          consequence={REPLACE_CONSEQUENCE}
          confirmLabel={REPLACE_CREDENTIAL}
          cancelLabel={KEEP_CREDENTIAL}
          busy={busy}
          onConfirm={() => {
            send();
          }}
          onCancel={() => {
            setPending(false);
          }}
        />
      ) : null}
    </section>
  );
}

/** A leaver's agents, and the one act a reader may take on each. */
function Transfers() {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(TRANSFERS_API_PATH, version);
  const waiting = readTransfers(answer.data);
  const [chosen, setChosen] = useState<Transfer | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const take = useCallback((agentId: string) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(transferApiPath(agentId), { method: "POST" });
      setBusy(false);
      setChosen(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setVersion((one) => one + 1);
    })();
  }, []);

  if (answer.failure !== null) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return null;
  }
  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {waiting.length === 0 ? (
        <p className="note">{NO_TRANSFERS}</p>
      ) : (
        <>
          <p className="note">{STOPPED_UNTIL_TAKEN}</p>
          <ul className="roster" aria-label={WAITING_FOR_AN_OWNER}>
            {waiting.map((one) => (
              <li key={one.agent_id}>
                {one.display_name} <code>{one.agent_id}</code> <Chip label={one.owner_id} />{" "}
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  aria-label={`${TAKE_ON}: ${one.agent_id}`}
                  onClick={() => {
                    setChosen(one);
                  }}
                >
                  {TAKE_ON}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {chosen === null ? null : (
        <ConfirmAction
          question={`Become the owner of ${chosen.display_name}?`}
          consequence={TAKE_ON_CONSEQUENCE}
          confirmLabel={TAKE_ON}
          cancelLabel={KEEP_WAITING}
          busy={busy}
          onConfirm={() => {
            take(chosen.agent_id);
          }}
          onCancel={() => {
            setChosen(null);
          }}
        />
      )}
    </>
  );
}

export function StaffSources() {
  // Bumped when a source is connected or its first sync applied, so the page reads what changed.
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => {
    setVersion((one) => one + 1);
  }, []);
  const answer = useResource<unknown>(STAFF_SOURCES_API_PATH, version);
  const page = readStaffSources(answer.data);

  return (
    <article className="page">
      <h1>{STAFF_SOURCES_HEADING}</h1>
      <p className="lede">{STAFF_SOURCES_LEDE}</p>

      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure} />
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : null}

      <ConnectStaffSource onConnected={refresh} />

      {/*
       * What the API answered, drawn only once it has answered. Read from a request still in
       * flight or one that failed, the reader returns no options, and the page used to say there
       * were no staff sources under a loading sentence and under a failure: three states, one
       * sentence. `tests/screen-states.test.tsx` found it.
       */}
      {answer.busy || answer.failure !== null ? null : (
        <>
          {page.selection === null || page.selection === undefined ? null : (
            <section className="card">
              <h2>{WHAT_THIS_INSTALL_READS}</h2>
              <p>
                <Chip label={page.selection.name} />
              </p>
              {page.selection.meaning === "" ? null : <p>{page.selection.meaning}</p>}
              {/*
               * The refusal is the API's own sentence, carried whole. It is
               * `brain.identity.staff_source.selected_source`'s message and it names the settings
               * nobody supplied, which is what somebody reading this screen has to act on; a
               * console that summarised it would be a second account of a configuration.
               */}
              {page.selection.ready ? null : (
                <Notice title={THE_SOURCE_REFUSED}>
                  <p>{page.selection.refusal}</p>
                </Notice>
              )}
              {page.selection.unsupplied.length === 0 ? null : (
                <dl className="fields" aria-label={STILL_TO_SET}>
                  <div className="fields__row">
                    <dt>{STILL_TO_SET}</dt>
                    <dd>
                      {page.selection.unsupplied.map((name) => (
                        <Chip key={name} label={name} />
                      ))}
                    </dd>
                  </div>
                </dl>
              )}
            </section>
          )}

          <section className="card">
            <h2>{WHAT_IT_COULD_READ}</h2>
            {page.options.length === 0 ? (
              <p className="note">{NO_SOURCES}</p>
            ) : (
              <ul className="roster" aria-label={SOURCES_LIST_LABEL}>
                {page.options.map((option) => (
                  <Option key={option.name} option={option} />
                ))}
              </ul>
            )}
          </section>

          {page.how_to_choose === "" ? null : (
            <section className="card">
              <h2>{WHERE_THE_CHOICE_IS_MADE}</h2>
              <p>{page.how_to_choose}</p>
            </section>
          )}
        </>
      )}

      <section className="card">
        <h2>{TRY_IT_BEFORE_IT_RUNS}</h2>
        <Trial />
      </section>

      <section className="card">
        <h2>{NIGHTLY_SYNC}</h2>
        <NightlySync version={version} />
      </section>

      <SyncCredential />

      <section className="card">
        <h2>{WAITING_FOR_AN_OWNER}</h2>
        <Transfers />
      </section>
    </article>
  );
}
