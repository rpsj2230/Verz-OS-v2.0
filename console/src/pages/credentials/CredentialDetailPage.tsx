/**
 * One credential's page on the shared kit, in SCREEN 14's shape: a header with its figures, and three
 * views, Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/credentials/{family}/{name}` is the Dashboard; `/profile` and `/about` below
 * it are the other two. Any other view name opens the Dashboard silently, the agent page's rule: an
 * address typed to probe for a view lands where the bare address does.
 *
 * **One request for the page**, `GET /api/v1/credentials/{family}/{name}`, which carries the slot,
 * its vault, what it is for, its last use where anything records one, and its history. A save asks
 * for it again under a new version, so the figures and the history move without a reload. A 404 is
 * not explained: a slot this install does not declare and a reader who may not manage credentials
 * are one answer, from `brain.credential_routes`.
 *
 * **The figures are what a table records, and a figure nothing records is said to be so.** Last set
 * is the vault's own time for the value held; last used is left out as "Not recorded yet", with the
 * API's reason, for a kind nothing records a use of; the count of changes is the ledger's entries
 * this page lists, never a count of anything the reader was not shown.
 *
 * Task ids: M27.11.10, M27.15.50, M27.16.1
 */

import { IdCard, Info, LayoutDashboard } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  DetailHeader,
  DetailPage,
  FailureState,
  KpiStrip,
  LoadingState,
  StatCard,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { CREDENTIALS_HEADING } from "./CredentialsPage";
import {
  CREDENTIALS_ADDRESS,
  READ_BY_WORDS,
  credentialAddress,
  credentialApiPath,
  kindWords,
  readCredentialDetail,
  whenWords,
} from "./credentialRows";
import { CredentialAbout, CredentialDashboard, CredentialProfile, SET_VALUE_ANCHOR } from "./CredentialViews";
import { OutrankedPill, StatePill, VaultCard } from "./parts";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type CredentialView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<CredentialView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Credential views";
export const LOADING_CREDENTIAL = "Loading this credential.";
export const FIGURES_LABEL = "This credential at a glance";
export const LAST_SET = "Last set";
export const LAST_USED = "Last used";
export const CHANGES = "Changes recorded";
export const SET_BUTTON = "Set a value";
export const REPLACE_BUTTON = "Replace the value";

const VIEW_ICONS: Readonly<Record<CredentialView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** Where a view of a slot is. The Dashboard is the bare address. */
export function viewAddress(slot: string, view: CredentialView): string {
  return view === VIEWS[0] ? credentialAddress(slot) : `${credentialAddress(slot)}/${view}`;
}

/** Which view an address opens. */
export function viewFor(view: string | undefined): CredentialView {
  return view === "profile" || view === "about" ? view : "dashboard";
}

export function CredentialDetailPage({ slot, view }: { readonly slot: string; readonly view: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [saved, setSaved] = useState<string | null>(null);
  const answer = useResource<unknown>(credentialApiPath(slot), version);
  const onSaved = useCallback((sentence: string) => {
    setSaved(sentence);
    setVersion((count) => count + 1);
  }, []);

  // A save asks again under a new version; the page stays drawn while it does.
  const detail = readCredentialDetail(answer.data);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (detail === null) {
    return answer.busy ? <LoadingState label={LOADING_CREDENTIAL} /> : null;
  }
  const { row } = detail;
  const shown = viewFor(view);
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(slot, one), icon: <Icon aria-hidden /> };
  });
  const headingId = `credential-${slot.replace(/[^a-z0-9_-]/giu, "-")}`;
  const subline = [kindWords(row.kind), row.readBy === undefined ? null : `read by ${(READ_BY_WORDS[row.readBy] ?? row.readBy).toLowerCase()}`]
    .filter((one): one is string => one !== null)
    .join(" · ");

  const header = (
    <DetailHeader
      name={row.holder}
      headingId={headingId}
      pills={
        <>
          <StatePill state={row.state} />
          {row.outrankedBy === undefined ? null : <OutrankedPill variable={row.outrankedBy} />}
        </>
      }
      subline={subline}
      actions={
        row.writable ? (
          <Button asChild size="sm" className="min-h-11 no-underline sm:min-h-8">
            <Link to={`${viewAddress(slot, "profile")}#${SET_VALUE_ANCHOR}`}>{row.held === true ? REPLACE_BUTTON : SET_BUTTON}</Link>
          </Button>
        ) : undefined
      }
      figures={
        <KpiStrip label={FIGURES_LABEL} count={3}>
          <StatCard label={LAST_SET} value={whenWords(row.setAt)} />
          <StatCard
            label={LAST_USED}
            value={whenWords(detail.lastUsedAt)}
            unrecordedWhy={detail.useRecorded ? undefined : detail.lastUsedTold}
          />
          <StatCard
            label={CHANGES}
            value={detail.history === null ? undefined : String(detail.history.length)}
            unrecordedWhy={detail.history === null ? detail.historyTold : undefined}
          />
        </KpiStrip>
      }
    />
  );

  return (
    <DetailPage
      crumbs={[{ label: CREDENTIALS_HEADING, to: CREDENTIALS_ADDRESS }, { label: row.holder }]}
      header={header}
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={shown} />}
    >
      <div className="flex min-w-0 flex-col gap-4">
        {shown === "dashboard" ? (
          <>
            <CredentialDashboard detail={detail} />
            {detail.vault === null ? null : <VaultCard vault={detail.vault} />}
          </>
        ) : null}
        {shown === "profile" ? <CredentialProfile detail={detail} saved={saved} onSaved={onSaved} /> : null}
        {shown === "about" ? <CredentialAbout detail={detail} /> : null}
      </div>
    </DetailPage>
  );
}
