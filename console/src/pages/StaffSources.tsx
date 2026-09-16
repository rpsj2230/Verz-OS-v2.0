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
 * **There is no picker and no text box, and the screen says why rather than looking
 * unfinished.** See `staffSourcesQuery.A_CONTROL_THAT_POSTS_TO_NOTHING_IS_WORSE_THAN_NO_CONTROL`.
 * The design's Connectors screen carries an "Add connector" action in its bar; the equivalent
 * here would post to nothing, because the choice is an installation setting no route writes.
 *
 * **There is no figure anywhere on it**, which is the one convention of the design this screen
 * cannot keep. See `staffSourcesQuery.THE_DESIGN_COUNTS_AND_THIS_SCREEN_CANNOT`.
 *
 * **No tone is computed from a value.** `ui/Status.tsx` is the only module allowed to turn a
 * payload into a colour and its vocabulary is the four connector health words, none of which a
 * staff source has. So a source's state is the API's own sentence and a chosen source is marked
 * with a badge whose tone is written at the call site, which is `ui/Badge.tsx`'s rule.
 *
 * Imported statically rather than split, for `Scopes`' reason: neither heavy library and no
 * stylesheet of its own.
 *
 * M27.7.2 is this screen and is deliberately not claimed. The leaf asks for a staff source to be
 * chosen, configured and tried, and this page does none of the three: the first two are writes
 * the API does not have and the third answers a sentence on every install today. See
 * `brain.staff_source_routes`, which declines it in the same words, and `pages/Recovery.tsx`,
 * which declines M27.7.26 for the same shape.
 *
 * Task ids: none
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Badge } from "../ui/Badge";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import {
  readStaffSources,
  readTrial,
  wasRead,
  STAFF_SOURCES_API_PATH,
  TRIAL_API_PATH,
  type Read,
  type SourceOption,
  type TrialAnswer,
  type TrialRun,
} from "./staffSourcesQuery";
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

export function StaffSources() {
  const answer = useResource<unknown>(STAFF_SOURCES_API_PATH);
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

          {page.not_written_here === "" ? null : (
            <section className="card">
              <h2>{WHERE_THE_CHOICE_IS_MADE}</h2>
              <p>{page.not_written_here}</p>
            </section>
          )}
        </>
      )}

      <section className="card">
        <h2>{TRY_IT_BEFORE_IT_RUNS}</h2>
        <Trial />
      </section>
    </article>
  );
}
