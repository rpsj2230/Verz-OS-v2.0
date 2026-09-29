/**
 * One service account on the shared page kit: its figures, its live keys with revoke, its
 * capabilities, and the acts that issue a key and retire it.
 *
 * **One view, not three.** An account has no runs of its own to chart and no history the API
 * serves beyond the ledger, so a Dashboard and an About would be empty frames; the page is the
 * header with its figures and the sections under it, which is SCREEN 14's shape without the switch.
 *
 * **Another person's account, a retired one and one that never existed are one answer**, the
 * route's 404, drawn as the API's sentence. The page names none of them.
 *
 * **Identifiers live in Advanced**: the account id is under the name because an integration quotes
 * it, and every key's handle is in the Advanced section rather than in the key table.
 *
 * Task ids: M27.11.5, M27.15.26, M27.16.1
 */

import { KeyRound, Plus } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  DetailHeader,
  DetailPage,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  NotOffered,
  SectionCard,
  StatCard,
  UnavailableAction,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { accountName, SERVICE_ACCOUNTS_API_PATH, SERVICE_ACCOUNTS_LABEL, when, type AccountRow } from "../serviceAccountsQuery";
import { EndingDialog, IssueKeyDrawer, type Ending } from "./AccountActs";
import { ACT_LABELS, NOT_HELD_MARK, NOT_OFFERED, UNAVAILABLE } from "./serviceAccountActions";

export const READING_ACCOUNT = "Reading this service account.";
export const UNREADABLE_ACCOUNT = "The answer could not be read as a service account.";
export const KEYS_HEADING = "Live keys";
export const KEYS_LEDE = "Each key calls this system as this account until it stops working or is revoked.";
export const NO_KEYS = "No live key";
export const NO_KEYS_DESCRIPTION = "Issue a key to let the integration call this system.";
export const CAPABILITIES_HEADING = "What it may use";
export const CAPABILITIES_LEDE = "Never more than you hold. A capability you do not hold now is marked and does nothing.";
export const NOT_HELD_NOW = "You do not hold these now, so the account cannot use them:";

/** Read one `AccountView`, or null when the body is not one. */
export function readAccount(payload: unknown): AccountRow | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<AccountRow>;
  return typeof body.client_id === "string" && Array.isArray(body.keys) && Array.isArray(body.ceiling)
    ? (payload as AccountRow)
    : null;
}

export function accountApiPath(clientId: string): string {
  return `${SERVICE_ACCOUNTS_API_PATH}/${encodeURIComponent(clientId)}`;
}

function AccountView({ account, onChanged }: { readonly account: AccountRow; readonly onChanged: (told: string | null) => void }) {
  const navigate = useNavigate();
  const [issuing, setIssuing] = useState(false);
  const [ending, setEnding] = useState<Ending | null>(null);
  const name = accountName(account);
  const headingId = "service-account-heading";
  return (
    <DetailPage
      crumbs={[{ label: SERVICE_ACCOUNTS_LABEL, to: "/service-accounts" }, { label: name }]}
      header={
        <DetailHeader
          name={name}
          headingId={headingId}
          pills={<Chip tone="brand">Active</Chip>}
          subline={account.label.trim() === "" ? undefined : account.client_id}
          actions={
            <>
              <UnavailableAction label={ACT_LABELS.changeEnd} text={ACT_LABELS.changeEnd} reason={UNAVAILABLE.changeEnd.reason} />
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={() => {
                  setEnding({ kind: "retire", account });
                }}
              >
                {ACT_LABELS.retire}
              </Button>
              <Button
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={() => {
                  setIssuing(true);
                }}
              >
                <Plus aria-hidden />
                {ACT_LABELS.issue}
              </Button>
            </>
          }
          figures={
            <KpiStrip label="This account's figures" count={4}>
              <StatCard label="Live keys" value={String(account.keys.length)} sub="at most two at once" />
              <StatCard label="Capabilities" value={String(account.ceiling.length)} />
              <StatCard label="Stops working" value={when(account.lapses_at).slice(0, 10)} sub={when(account.lapses_at).slice(11)} />
              <StatCard label="Registered" value={when(account.created_at).slice(0, 10)} />
            </KpiStrip>
          }
        />
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title={KEYS_HEADING} lede={KEYS_LEDE} footer={<NotOffered>{NOT_OFFERED.rotate}</NotOffered>}>
          {account.keys.length === 0 ? (
            <EmptyState title={NO_KEYS} description={NO_KEYS_DESCRIPTION} icon={<KeyRound aria-hidden />} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Issued</TableHead>
                  <TableHead>Stops working</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {account.keys.map((key) => (
                  <TableRow key={key.handle}>
                    <TableCell className="whitespace-normal">{key.label.trim() === "" ? "Unnamed key" : key.label}</TableCell>
                    <TableCell className="font-mono text-[12px]">{when(key.issued_at)}</TableCell>
                    <TableCell className="font-mono text-[12px]">{when(key.lapses_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        className="min-h-11 sm:min-h-8"
                        aria-label={`${ACT_LABELS.revoke} ${key.label.trim() === "" ? "unnamed key" : key.label}`}
                        onClick={() => {
                          setEnding({ kind: "revoke", account, key });
                        }}
                      >
                        {ACT_LABELS.revoke}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </SectionCard>
        <SectionCard title={CAPABILITIES_HEADING} lede={CAPABILITIES_LEDE}>
          <div className="flex flex-col gap-2">
            <span className="flex flex-wrap gap-1">
              {account.ceiling.map((one) => (
                <Chip key={one} mono>
                  {account.not_held_now.includes(one) ? `${one} ${NOT_HELD_MARK}` : one}
                </Chip>
              ))}
            </span>
            {account.not_held_now.length === 0 ? null : (
              <Note kind="not-yet">
                {NOT_HELD_NOW} {account.not_held_now.join(", ")}.
              </Note>
            )}
          </div>
        </SectionCard>
        <SectionCard title="Owner">
          <NotOffered>{NOT_OFFERED.changeOwner}</NotOffered>
        </SectionCard>
        <Advanced>
          <FactList>
            <Fact label="Account ID">
              <span className="font-mono text-[12px]">{account.client_id}</span>
            </Fact>
            {account.keys.map((key) => (
              <Fact key={key.handle} label={key.label.trim() === "" ? "Unnamed key" : key.label}>
                <span className="font-mono text-[12px]">{key.handle}</span>
              </Fact>
            ))}
          </FactList>
        </Advanced>
      </div>
      {issuing ? (
        <IssueKeyDrawer
          account={account}
          onClose={() => {
            setIssuing(false);
          }}
          onDone={() => {
            setIssuing(false);
            onChanged(null);
          }}
        />
      ) : null}
      <EndingDialog
        ending={ending}
        onClose={() => {
          setEnding(null);
        }}
        onDone={(done, told) => {
          setEnding(null);
          if (done.kind === "retire") {
            navigate("/service-accounts");
            return;
          }
          onChanged(told);
        }}
      />
    </DetailPage>
  );
}

export function ServiceAccountDetailPage({ clientId }: { readonly clientId: string }) {
  const location = useLocation();
  const arrived = (location.state as { told?: unknown } | null)?.told;
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(typeof arrived === "string" ? arrived : null);
  const answer = useResource<unknown>(accountApiPath(clientId), version);

  if (answer.busy && answer.data === null) {
    return <LoadingState label={READING_ACCOUNT} />;
  }
  if (answer.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <h1 className="m-0 font-heading text-[22px] font-semibold text-ink">{SERVICE_ACCOUNTS_LABEL}</h1>
        <FailureState failure={answer.failure} />
      </div>
    );
  }
  const account = readAccount(answer.data);
  if (account === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <h1 className="m-0 font-heading text-[22px] font-semibold text-ink">{SERVICE_ACCOUNTS_LABEL}</h1>
        <Note>{UNREADABLE_ACCOUNT}</Note>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      <AccountView
        account={account}
        onChanged={(sentence) => {
          setTold(sentence);
          setVersion((count) => count + 1);
        }}
      />
    </div>
  );
}
