/**
 * A person's History: every entry in the audit trail about them that this reader may read, oldest
 * first, each said in words (M27.15.18).
 *
 * **The audit screen's own route decides every entry.** `GET /audit/history` narrows the ledger to
 * this person's subject and to what the reader's own grants let them read, so an entry this reader may
 * not read is absent, and nothing here counts what was left out. A reader who may not open the audit
 * trail at all is shown that route's refusal in its own words.
 *
 * **Who did it is a name, never an identifier.** The actor is looked up in the directory as this
 * reader may see it; somebody the reader may not see, and the system's own account, read as "another
 * account", which says nothing the entry did not already say.
 *
 * Task ids: M27.15.18, M27.16.1
 */

import { History } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { EmptyState, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { phraseFor } from "../auditQuery";
import { whenWords } from "../access/formParts";
import { PersonName, useNames } from "../access/PersonName";
import { WORKS_AT } from "./peopleActions";
import { historyApiPath, readHistory, type PersonDetail } from "./peopleQuery";

export const HISTORY_HEADING = "History";
export const NO_HISTORY = "Nothing recorded that you may read";
export const NO_HISTORY_DESCRIPTION = "Grants, placements, sign-ins and changes to their standing are recorded here as they happen.";

export function PersonHistory({ detail }: { readonly detail: PersonDetail }) {
  const { person } = detail;
  const answer = useResource<unknown>(historyApiPath(person.principalId));
  const history = useMemo(() => readHistory(answer.data), [answer.data]);
  const names = useNames(history.events.length > 0);

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading their history." rows={3} />;
  } else if (history.events.length === 0) {
    body = <EmptyState title={NO_HISTORY} description={NO_HISTORY_DESCRIPTION} icon={<History aria-hidden />} />;
  } else {
    body = (
      <ol className="m-0 flex list-none flex-col divide-y divide-line p-0">
        {history.events.map((one, index) => (
          <li key={`${one.at} ${one.action} ${String(index)}`} className="flex flex-col gap-0.5 py-2 text-[13px]">
            <span className="text-ink">
              <PersonName
                principalId={one.actorId}
                names={names}
                known={one.actorId === person.principalId ? person.displayName : undefined}
                link={false}
              />{" "}
              {phraseFor(one.action, one.details)} {person.displayName}
            </span>
            <span className="text-[12px] text-dim">{whenWords(one.at)}</span>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <SectionCard
      title={HISTORY_HEADING}
      lede="What was changed about them, and by whom, oldest first."
      action={
        <Link to={WORKS_AT.audit} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
          Audit trail
        </Link>
      }
      footer={history.full ? <Note>The history shown is the most one page holds; the audit trail has the rest.</Note> : undefined}
    >
      {body}
    </SectionCard>
  );
}
