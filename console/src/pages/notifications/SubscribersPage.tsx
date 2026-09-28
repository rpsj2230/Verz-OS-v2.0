/**
 * Subscribers, a tab of Notifications and email, on the page kit: every outside address this
 * install tells when something happens here, what each is told about, and when it was last told.
 * Read only.
 *
 * **Who is told is `brain.console.subscribers`' answer.** A reader who may not manage subscribers
 * is sent what an install with none is sent, so this page says "No subscribers to show" to both.
 * Each subscriber links to its page under Webhooks, where it is changed; a second set of controls
 * here would be a second place for their confirmations to drift.
 *
 * **What was removed from the old screen, and why.** The breadcrumb as text; the principal id of
 * whoever set each subscriber up (named on the subscriber's page now, the id under Advanced there);
 * and the kind and state filters that narrowed one answer in the browser, which the list's column
 * choice and export replace for a list this short.
 *
 * Task ids: M27.7.12, M27.16.1
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Note, type EntityColumn } from "../../components/kit";
import { GROUP_LABEL } from "../channelsQuery";
import { SUBSCRIBERS_API_PATH, readSubscribers, type SubscriberRow } from "../governPeopleQuery";
import { at, Line, OpsPage, WholeList } from "../operations/parts";
import { webhookAddress } from "../webhooksQuery";
import { OFF_WORD, ON_WORD, SubscriberPill } from "../webhooks/pills";

export const SUBSCRIBERS_HEADING = "Subscribers";
export const SUBSCRIBERS_LEDE = "Every outside address this install tells when something happens here, and what each is told about.";
export const READING_SUBSCRIBERS = "Loading who is told what.";
export const NO_SUBSCRIBERS = "No subscribers to show";
export const NO_SUBSCRIBERS_DESCRIPTION = "A subscriber registered under Webhooks appears here.";
export const NEVER_DELIVERED = "Never";

const COLUMNS: readonly EntityColumn<SubscriberRow>[] = [
  {
    id: "subscriber",
    header: "Subscriber",
    hideable: false,
    cell: (row) => (
      <Link to={webhookAddress(row.subscriber_id)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
        {row.subscriber_id}
      </Link>
    ),
    text: (row) => row.subscriber_id,
  },
  { id: "endpoint", header: "Address", cell: (row) => <span className="font-mono text-[12px]">{row.endpoint}</span>, text: (row) => row.endpoint },
  { id: "kinds", header: "Told about", cell: (row) => row.kinds.join(", "), text: (row) => row.kinds.join(", ") },
  { id: "state", header: "State", cell: (row) => <SubscriberPill active={row.active} />, text: (row) => (row.active ? ON_WORD : OFF_WORD) },
  {
    id: "delivered",
    header: "Last delivered",
    cell: (row) => (row.last_delivered_at === null ? NEVER_DELIVERED : at(row.last_delivered_at)),
    text: (row) => (row.last_delivered_at === null ? NEVER_DELIVERED : at(row.last_delivered_at)),
  },
];

export function SubscribersPage() {
  const answer = useResource<unknown>(SUBSCRIBERS_API_PATH);
  const page = answer.data === null ? null : readSubscribers(answer.data);
  return (
    <OpsPage
      crumbs={[{ label: GROUP_LABEL }, { label: SUBSCRIBERS_HEADING }]}
      title={SUBSCRIBERS_HEADING}
      lede={SUBSCRIBERS_LEDE}
      loading={READING_SUBSCRIBERS}
      busy={answer.busy}
      failure={answer.failure}
      body={page}
    >
      {(body) => (
        <>
          {body.findings.length === 0 ? null : (
            <div className="flex flex-col gap-1">
              {body.findings.map((one) => (
                <Note key={one}>{one}</Note>
              ))}
            </div>
          )}
          <WholeList
            title={SUBSCRIBERS_HEADING}
            caption={SUBSCRIBERS_HEADING}
            columns={COLUMNS}
            rows={body.rows}
            rowId={(row) => row.subscriber_id}
            rowLabel={(row) => row.subscriber_id}
            exportName="subscribers"
            empty={NO_SUBSCRIBERS}
            emptyDescription={NO_SUBSCRIBERS_DESCRIPTION}
            footer={
              <>
                {body.stopping === "" ? null : <Line>{body.stopping}</Line>}
                {body.scope === "" ? null : <Line>{body.scope}</Line>}
              </>
            }
          />
        </>
      )}
    </OpsPage>
  );
}
