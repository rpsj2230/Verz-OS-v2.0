/**
 * Memory: what the system remembers about one person, in its own words, and every change to it.
 *
 * **A Govern screen rather than a tab inside an agent, although that is where the design draws
 * it.** SCREEN 13 of `docs/screens.html` puts Memory in the menu inside one agent and draws a
 * memory card on that agent's page; the design has no company-level memory screen at all. The
 * decision this screen is served by is `brain.console.govern_estate.subject_memory`, which is
 * keyed by the person a memory is about, `brain.console.screens` registers Memory under Govern,
 * and neither memory table records which agent was running when a memory formed, so a tab inside
 * an agent would have nothing to select on. `memoryQuery.ts` gives the argument in full.
 *
 * **What is drawn is the design's memory card, opened for one person.** Curated beside extracted
 * with the size of each and how many entries it holds, the last revision, and the design's own
 * sentence that memory is readable text with a diff per revision, followed by the statements
 * themselves and the change history the card links to. The design's "Learning tiers active" row
 * is a setting of an agent, and the card says so rather than showing a person a value for it.
 *
 * **One person at a time, and never a list to choose from.** The address is the whole of the
 * state: `/memory` asks for a reference and `/memory/{reference}` is that person's memory, so a
 * colleague can be sent the page being argued about. A list of the people there is memory about
 * would be a directory of people, which the decision refuses to be.
 *
 * **Nothing here edits or deletes a memory, and the page says why.** An edit and a delete both
 * write a correction beside the memory they change, and nothing on this install stores one. For
 * the same reason no revision carries a diff yet: nothing records what a memory replaced.
 *
 * **Nothing here decides who may read anything.** A memory this reader may not recall is absent,
 * and the page for a person with such memories is identical to the page for a person with none,
 * because the API made them identical. A failure is the API's own sentence and the trace id.
 *
 * Imported statically rather than split, which is `Roles.tsx`' rule.
 *
 * Task ids: M27.7.22
 */

import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import {
  dayOf,
  kilobytes,
  latestRevision,
  memoryAddress,
  memoryApiPath,
  readMemoryPage,
  referenceProblem,
  type RememberedText,
} from "./memoryQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The design's own label for this screen. */
export const MEMORY_HEADING = "Memory";

/** Under the heading. The design's own sentence about what memory is on this system. */
export const MEMORY_LEDE =
  "Memory is readable text with a diff per revision, not an opaque store. If the system believes " +
  "something wrong about somebody, you can see the sentence.";

/** Before anybody has been named. */
export const ONE_PERSON_AT_A_TIME =
  "Memory is read one person at a time. There is no list of the people the system remembers " +
  "things about, because that list would be a directory of people.";

/** A person this reader can read nothing about, whichever of the reasons that is. */
export const NOTHING_TO_READ = "There is nothing remembered about this person that you can read.";

/** An empty half of the card. Says nothing about memories this reader may not recall. */
export const NONE_ON_THIS_SIDE = "Nothing to show.";

/** In place of the edit and delete controls. */
export const EDIT_NOT_OFFERED =
  "A memory cannot be edited or deleted from this screen. Either one writes a correction beside " +
  "the memory it changes, so the old sentence stays on the record, and nothing on this install " +
  "stores a correction yet.";

/** Beside the history, while corrections are not recorded. */
export const NO_DIFFS_YET =
  "No revision here shows a change yet. A change is recorded as a newer memory replacing an older " +
  "one, and nothing on this install records what a memory replaced, so each entry is the moment a " +
  "memory was formed.";

/** In place of the design's "Learning tiers active" row. */
export const TIERS_ARE_PER_AGENT =
  "Which tiers learn is set on an agent, not on a person, so it is not shown here.";

/** The bound on the load, in words, identical for every person. */
export function consideredSentence(perKind: number): string {
  return (
    `This page reads at most the ${String(perKind)} most recent stated memories and the ` +
    `${String(perKind)} most recent inferred memories about a person.`
  );
}

/** The design's own row: size and entries, over the statements this reader was shown. */
function sizeOf(texts: readonly RememberedText[]): string {
  return texts.length === 0
    ? NONE_ON_THIS_SIDE
    : `${kilobytes(texts)} KB, ${String(texts.length)} ${texts.length === 1 ? "entry" : "entries"}`;
}

function Statements({
  heading,
  texts,
}: {
  readonly heading: string;
  readonly texts: readonly RememberedText[];
}) {
  return (
    <section className="card">
      <h2>{heading}</h2>
      {texts.length === 0 ? (
        <p className="note">{NONE_ON_THIS_SIDE}</p>
      ) : (
        <dl className="fields" aria-label={heading}>
          {texts.map((one) => (
            <div className="fields__row" key={one.memory_id}>
              <dt>
                <time dateTime={one.formed_at}>{dayOf(one.formed_at)}</time>
              </dt>
              <dd>
                <span>{one.statement}</span>
                <p className="note">
                  <code>{one.memory_id}</code>, confidence {one.confidence.toFixed(2)}
                </p>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function MemoryAnswerView({ subject }: { readonly subject: string }) {
  const answer = useResource<unknown>(memoryApiPath(subject));

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readMemoryPage(answer.data, subject);
  const last = latestRevision(page.history);
  const readable = page.curated.length + page.extracted.length > 0;

  return (
    <>
      {page.staleness === null ? null : <p className="note">{page.staleness}</p>}

      <section className="card">
        <h2>
          Memory about <code>{page.subject}</code>
        </h2>
        <dl className="fields" aria-label="Memory at a glance">
          <div className="fields__row">
            <dt>Curated, stated by a person</dt>
            <dd>
              <span>{sizeOf(page.curated)}</span>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Extracted from conversations</dt>
            <dd>
              <span>{sizeOf(page.extracted)}</span>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Last revision</dt>
            <dd>
              {last === null ? (
                <span>{NONE_ON_THIS_SIDE}</span>
              ) : (
                <time dateTime={last.at}>{dayOf(last.at)}</time>
              )}
            </dd>
          </div>
          <div className="fields__row">
            <dt>Learning tiers active</dt>
            <dd>
              <p className="note">{TIERS_ARE_PER_AGENT}</p>
            </dd>
          </div>
        </dl>
        {readable ? null : <p className="note">{NOTHING_TO_READ}</p>}
        {page.editIsNotWritable ? <p className="note">{EDIT_NOT_OFFERED}</p> : null}
      </section>

      <Statements heading="Curated" texts={page.curated} />
      <Statements heading="Extracted from conversations" texts={page.extracted} />

      <section className="card">
        <h2>Change history</h2>
        {page.correctionsAreNotRecorded ? <p className="note">{NO_DIFFS_YET}</p> : null}
        {page.history.length === 0 ? (
          <p className="note">{NONE_ON_THIS_SIDE}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">Revisions you can read, oldest first</caption>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Memory</th>
                  <th scope="col">Replaced</th>
                  <th scope="col">What changed</th>
                  <th scope="col">Why</th>
                </tr>
              </thead>
              <tbody>
                {page.history.map((one) => (
                  <tr key={one.memory_id}>
                    <td>
                      <time dateTime={one.at}>{dayOf(one.at)}</time>
                    </td>
                    <td>
                      <code>{one.memory_id}</code>
                    </td>
                    <td>{one.replaced_id === null ? "" : <code>{one.replaced_id}</code>}</td>
                    <td>
                      {one.diff.length === 0 ? (
                        "formed"
                      ) : (
                        <ul>
                          {one.diff.map((line, index) => (
                            <li key={`${one.memory_id}-${String(index)}`}>
                              <code>{line}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>{[one.correction, one.trigger].filter(Boolean).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">{consideredSentence(page.consideredPerKind)}</p>
      </section>
    </>
  );
}

function LookUp({ current }: { readonly current: string }) {
  const navigate = useNavigate();
  const [typed, setTyped] = useState(current);
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = referenceProblem(typed);
    setProblem(found);
    if (found === null) {
      navigate(memoryAddress(typed));
    }
  }

  return (
    <form className="form card" onSubmit={submit} noValidate>
      <label className="control-label" htmlFor="memory-subject">
        Person
      </label>
      <p className="field-description" id="memory-subject-help">
        The person's reference, as the People and grants screen shows it without the word
        principal in front.
      </p>
      <input
        id="memory-subject"
        className="form-control"
        type="text"
        autoComplete="off"
        spellCheck={false}
        aria-describedby="memory-subject-help"
        aria-invalid={problem === null ? undefined : true}
        value={typed}
        onChange={(event) => {
          setTyped(event.target.value);
        }}
      />
      {problem === null ? null : <p className="note">{problem}</p>}
      <div className="form-actions">
        <button className="button" type="submit">
          Read memory
        </button>
      </div>
    </form>
  );
}

export function Memory() {
  const { subject } = useParams();

  return (
    <article className="page">
      <h1>{MEMORY_HEADING}</h1>
      <p className="lede">{MEMORY_LEDE}</p>
      <LookUp key={subject ?? ""} current={subject ?? ""} />
      {subject === undefined || referenceProblem(subject) !== null ? (
        <p className="note">{ONE_PERSON_AT_A_TIME}</p>
      ) : (
        <MemoryAnswerView subject={subject} />
      )}
    </article>
  );
}
