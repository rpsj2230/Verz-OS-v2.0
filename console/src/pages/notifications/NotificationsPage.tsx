/**
 * Notifications and email, on the page kit: every notice this product composes, who it tells and
 * whether anything sends it yet, the switch that stops one, and the relay mail goes through.
 *
 * **Notices are a list answered whole**, the product's own declaration, so they are
 * `kit/EntityTable` in a card with column choice and export, and no search box a route would
 * ignore. A notice with no switch says so in its row ("Always on", with the API's reason on hover),
 * because a disabled switch would say it could be switched.
 *
 * **The relay is one card of facts and four acts**: edit it, replace its password, send a test
 * message, and remove it, each in a drawer or a dialog confirmed in the API's words
 * (`RelayActs.tsx`). Removing it is new (`POST /notifications/relay/removal`), and is offered only
 * while a relay is saved.
 *
 * **People are named, never shown by id**: whoever switched a notice, saved the relay or keeps
 * being refused (an alert's colleague) is a name from the API's `people`, and the ids are under
 * Advanced.
 *
 * **What was removed from the old screen, and why.** The breadcrumb as text; the principal ids
 * beside every switch and the relay's writer; the relay, password and test forms always open one
 * under another (drawers now); the empty alerts card and its sentence, drawn now only when an alert
 * was kept for the reader; and three served sentences under the notices, which are the card's one
 * line and a footer.
 *
 * Task ids: M27.8.11, M23.2.2, M27.16.1
 */

import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Advanced, Fact, FactList, Note, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { GROUP_LABEL } from "../channelsQuery";
import { at, Line, OpsPage, WholeList } from "../operations/parts";
import {
  NOTIFICATIONS_API_PATH,
  passwordWord,
  personWords,
  readAlerts,
  readNotifications,
  sentSentence,
  type AlertRow,
  type NoticeRow,
  type NotificationsBody,
} from "../notificationsQuery";
import { WEBHOOKS_PATH } from "../webhooksQuery";
import { NoticePill, SentPill } from "./pills";
import {
  EDIT_RELAY_LABEL,
  NoticeSwitchDialog,
  passwordLabel,
  PasswordDrawer,
  REMOVE_LABEL,
  RelayDrawer,
  RemoveRelayDialog,
  SET_UP_RELAY_LABEL,
  SWITCH_OFF_LABEL,
  SWITCH_ON_LABEL,
  TRIAL_LABEL,
  TrialDrawer,
} from "./RelayActs";

export const NOTIFICATIONS_HEADING = "Notifications and email";
export const NOTIFICATIONS_LEDE = "Who this install tells what, whether anything sends it yet, and the relay mail is sent through.";
export const READING_NOTIFICATIONS = "Loading who is told what.";
export const NOTICES_HEADING = "Notices";
export const NO_NOTICES = "No notices declared";
export const RELAY_HEADING = "Email relay";
export const RELAY_NOT_SAVED = "No relay is saved, so no mail is sent.";
export const ALERTS_HEADING = "A colleague keeps being refused";
export const ALWAYS_ON = "Always on";
export const SUBSCRIBERS_LINE = "Systems outside the company are told through webhook subscribers.";

type Open =
  | { readonly act: "relay" }
  | { readonly act: "password" }
  | { readonly act: "trial" }
  | { readonly act: "remove" }
  | { readonly act: "switch"; readonly row: NoticeRow };

function noticeColumns(page: NotificationsBody): readonly EntityColumn<NoticeRow>[] {
  return [
    { id: "notice", header: "Notice", hideable: false, cell: (row) => <span className="font-medium">{row.title}</span>, text: (row) => row.title },
    { id: "told", header: "Who is told", cell: (row) => row.told, text: (row) => row.told },
    { id: "about", header: "About", hidden: true, cell: (row) => row.about, text: (row) => row.about },
    { id: "how", header: "How", hidden: true, cell: (row) => row.how, text: (row) => row.how },
    { id: "sent", header: "Today", cell: (row) => <SentPill sent={row.sent} />, text: (row) => sentSentence(row) },
    {
      id: "switch",
      header: "Switch",
      cell: (row) =>
        row.switchable ? (
          <span className="flex flex-col gap-0.5">
            <NoticePill on={row.on} />
            {row.changed_at === null ? null : (
              <span className="text-[11.5px] text-dim">{`${at(row.changed_at)}, by ${personWords(page.people, row.changed_by)}`}</span>
            )}
          </span>
        ) : (
          <span className="text-[12.5px] text-dim" title={row.fixed_because}>
            {ALWAYS_ON}
          </span>
        ),
      text: (row) => (row.switchable ? (row.on ? "On" : "Off") : ALWAYS_ON),
    },
  ];
}

function alertColumns(page: NotificationsBody): readonly EntityColumn<AlertRow>[] {
  return [
    {
      id: "colleague",
      header: "Colleague",
      hideable: false,
      cell: (row) => personWords(page.people, row.subject),
      text: (row) => personWords(page.people, row.subject),
    },
    { id: "said", header: "What it looks like", cell: (row) => row.said, text: (row) => row.said },
    { id: "when", header: "When", cell: (row) => at(row.raised_at), text: (row) => at(row.raised_at) },
  ];
}

function Body({ page, onAct }: { readonly page: NotificationsBody; readonly onAct: (open: Open) => void }) {
  const alerts = readAlerts(page);
  const email = page.email;
  const named = [
    ...new Set(
      [
        ...page.notices.map((one) => one.changed_by),
        email.changed_by,
        ...("rows" in alerts ? alerts.rows.map((one) => one.subject) : []),
      ].filter((one): one is string => one !== null),
    ),
  ];
  return (
    <>
      {"rows" in alerts && alerts.rows.length > 0 ? (
        <WholeList
          title={ALERTS_HEADING}
          caption={ALERTS_HEADING}
          columns={alertColumns(page)}
          rows={alerts.rows}
          rowId={(row) => `${row.subject}:${row.raised_at}`}
          rowLabel={(row) => personWords(page.people, row.subject)}
          empty={ALERTS_HEADING}
        />
      ) : null}
      <WholeList
        title={NOTICES_HEADING}
        lede={page.ships_on}
        caption={NOTICES_HEADING}
        columns={noticeColumns(page)}
        rows={page.notices}
        rowId={(row) => row.kind}
        rowLabel={(row) => row.title}
        rowActions={(row) =>
          row.switchable ? (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              aria-label={`${row.on ? SWITCH_OFF_LABEL : SWITCH_ON_LABEL}: ${row.title}`}
              onClick={() => {
                onAct({ act: "switch", row });
              }}
            >
              {row.on ? SWITCH_OFF_LABEL : SWITCH_ON_LABEL}
            </Button>
          ) : null
        }
        exportName="notices"
        empty={NO_NOTICES}
        footer={
          <>
            <Line>{page.only_the_last_change_is_kept}</Line>
            {"unread" in alerts && alerts.unread !== "" ? <Line>{alerts.unread}</Line> : null}
          </>
        }
      />
      <SectionCard
        title={RELAY_HEADING}
        lede={page.email_used_for}
        action={
          <>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct({ act: "relay" });
              }}
            >
              {email.configured ? EDIT_RELAY_LABEL : SET_UP_RELAY_LABEL}
            </Button>
          </>
        }
        footer={
          <p className="m-0 text-[12.5px] text-dim">
            {SUBSCRIBERS_LINE}{" "}
            <Link to={WEBHOOKS_PATH} className="text-acc-text underline-offset-4 hover:underline">
              Open Webhooks
            </Link>
          </p>
        }
      >
        <div className="flex min-w-0 flex-col gap-3">
          {email.configured ? (
            <FactList>
              <Fact label="Relay">{`${email.host ?? ""}, port ${String(email.port ?? "")}, ${email.security === "tls" ? "TLS" : "STARTTLS"}`}</Fact>
              <Fact label="Sender">{email.sender}</Fact>
              {email.username === null || email.username === "" ? null : <Fact label="User name">{email.username}</Fact>}
              <Fact label="Password">{passwordWord(email)}</Fact>
              {email.changed_at === null ? null : (
                <Fact label="Last saved">{`${at(email.changed_at)}, by ${personWords(page.people, email.changed_by)}`}</Fact>
              )}
            </FactList>
          ) : (
            <Note>{RELAY_NOT_SAVED}</Note>
          )}
          {email.password.vault === "ready" ? null : <Note kind="not-yet">{email.password.vault_told}</Note>}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct({ act: "password" });
              }}
            >
              {passwordLabel(email.password.held)}
            </Button>
            {email.configured ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  onClick={() => {
                    onAct({ act: "trial" });
                  }}
                >
                  {TRIAL_LABEL}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="min-h-11 text-crit sm:min-h-8"
                  onClick={() => {
                    onAct({ act: "remove" });
                  }}
                >
                  {REMOVE_LABEL}
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </SectionCard>
      {named.length === 0 ? null : (
        <Advanced>
          <FactList>
            {named.map((id) => (
              <Fact key={id} label={personWords(page.people, id)}>
                <span className="font-mono text-[12px]">{id}</span>
              </Fact>
            ))}
          </FactList>
        </Advanced>
      )}
    </>
  );
}

export function NotificationsPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const answer = useResource<unknown>(NOTIFICATIONS_API_PATH, version);
  const page = answer.data === null ? null : readNotifications(answer.data);
  const done = useCallback((sentence: string) => {
    setOpen(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const close = useCallback(() => {
    setOpen(null);
  }, []);
  const act = useCallback((next: Open) => {
    setTold(null);
    setOpen(next);
  }, []);

  return (
    <>
      <OpsPage
        crumbs={[{ label: GROUP_LABEL }, { label: NOTIFICATIONS_HEADING }]}
        title={NOTIFICATIONS_HEADING}
        lede={NOTIFICATIONS_LEDE}
        notice={told === null || told === "" ? undefined : <Note kind="done">{told}</Note>}
        loading={READING_NOTIFICATIONS}
        busy={answer.busy}
        failure={answer.failure}
        body={page}
      >
        {(body) => <Body page={body} onAct={act} />}
      </OpsPage>
      {page === null || open === null ? null : open.act === "relay" ? (
        <RelayDrawer page={page} onClose={close} onDone={done} />
      ) : open.act === "password" ? (
        <PasswordDrawer page={page} onClose={close} onDone={done} />
      ) : open.act === "trial" ? (
        <TrialDrawer page={page} onClose={close} onDone={done} />
      ) : open.act === "remove" ? (
        <RemoveRelayDialog page={page} onClose={close} onDone={done} />
      ) : (
        <NoticeSwitchDialog page={page} row={open.row} onClose={close} onDone={done} />
      )}
    </>
  );
}
