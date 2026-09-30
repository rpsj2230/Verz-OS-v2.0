/**
 * Questions nothing answered that were handed to a person, below the requests on the Access requests
 * page (M8.3.2, M8.3.4): what was handed to the reader, and what the reader asked that was handed on.
 *
 * **Both lists are the reader's own and the API decides every row.** `GET /escalations` answers for
 * the caller alone, and `0168`'s policy is what admits a row: the asker's, the one it was routed to,
 * and while nobody was named for its queue, whoever is named now. Nothing here filters or counts.
 *
 * **What was handed to the reader shows the handoff and nothing more**: who asked, their question in
 * their own words, what was tried and what is needed, and by when. It is the same handoff their own
 * channel was sent, for somebody who reads the web application rather than a chat.
 *
 * **What the reader asked shows the one sentence they are told**, which the API changes once the
 * worker's expiry has marked it expired, so an asker whose question nobody picked up is told so here
 * rather than left waiting. It never names who the queue is handed to.
 *
 * Task ids: M8.3.2, M8.3.4
 */

import { useResource } from "../../api/useResource";
import { Chip, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { whenWords } from "../review/parts";

export const ESCALATIONS_API_PATH = "/escalations";
export const HANDED_HEADING = "Questions handed to a person";
export const HANDED_TO_YOU = "Handed to you";
export const YOURS_HANDED_ON = "Yours, handed on";
export const NOTHING_HANDED = "Nothing has been handed to you.";
export const NOTHING_OF_YOURS = "None of your questions has been handed to a person.";
export const READING_HANDED = "Reading the questions handed to a person.";

export interface Asked {
  readonly escalation_id: string;
  readonly queue: string;
  readonly question: string;
  readonly raised_at: string;
  readonly expires_at: string;
  readonly expired: boolean;
  readonly said: string;
}

export interface Handed {
  readonly escalation_id: string;
  readonly queue: string;
  readonly asker_id: string;
  readonly asker_name: string;
  readonly question: string;
  readonly tried: readonly string[];
  readonly needed: string;
  readonly raised_at: string;
  readonly expires_at: string;
  readonly expired: boolean;
}

export interface EscalationsAnswer {
  readonly asked: readonly Asked[];
  readonly handed: readonly Handed[];
  readonly told: string;
}

function HandedRow({ one }: { readonly one: Handed }) {
  return (
    <li className="flex min-w-0 flex-col gap-1 border-b border-line pb-3 last:border-b-0">
      <span className="[overflow-wrap:anywhere]">
        <span className="font-medium text-ink">{one.asker_name || one.asker_id}</span> asked, for {one.queue}, on {whenWords(one.raised_at)}
      </span>
      <span className="[overflow-wrap:anywhere] text-ink">{one.question}</span>
      <span className="text-[13px] text-dim">Needed: {one.needed}</span>
      <span className="flex flex-wrap gap-1">
        {one.tried.map((step) => (
          <Chip key={step} mono>
            {step}
          </Chip>
        ))}
      </span>
      <span className="text-[12.5px] text-dim">
        {one.expired ? `Nobody picked it up by ${whenWords(one.expires_at)}.` : `Pick it up by ${whenWords(one.expires_at)}.`}
      </span>
    </li>
  );
}

function AskedRow({ one }: { readonly one: Asked }) {
  return (
    <li className="flex min-w-0 flex-col gap-1 border-b border-line pb-3 last:border-b-0">
      <span className="[overflow-wrap:anywhere] text-ink">{one.question}</span>
      <span className="text-[13px] text-dim">
        {one.said} Asked {whenWords(one.raised_at)}.
      </span>
    </li>
  );
}

export function HandedToAPersonSection() {
  const answer = useResource<EscalationsAnswer>(ESCALATIONS_API_PATH);
  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label={READING_HANDED} />;
  } else {
    const found = answer.data;
    body = (
      <div className="flex min-w-0 flex-col gap-4">
        <section aria-label={HANDED_TO_YOU} className="flex min-w-0 flex-col gap-2">
          <h3 className="m-0 text-[13px] font-semibold text-ink">{HANDED_TO_YOU}</h3>
          {found.handed.length === 0 ? (
            <p className="m-0 text-dim">{NOTHING_HANDED}</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {found.handed.map((one) => (
                <HandedRow key={one.escalation_id} one={one} />
              ))}
            </ul>
          )}
        </section>
        <section aria-label={YOURS_HANDED_ON} className="flex min-w-0 flex-col gap-2">
          <h3 className="m-0 text-[13px] font-semibold text-ink">{YOURS_HANDED_ON}</h3>
          {found.asked.length === 0 ? (
            <p className="m-0 text-dim">{NOTHING_OF_YOURS}</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {found.asked.map((one) => (
                <AskedRow key={one.escalation_id} one={one} />
              ))}
            </ul>
          )}
        </section>
      </div>
    );
  }
  const told = answer.data?.told ?? "";
  return (
    <SectionCard title={HANDED_HEADING} lede={told === "" ? undefined : <Note>{told}</Note>}>
      {body}
    </SectionCard>
  );
}
