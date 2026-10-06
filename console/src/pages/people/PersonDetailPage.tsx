/**
 * One person's page on the shared kit: a header naming them with their standing and the figures
 * every view shares, and six views at addresses of their own, in the order the console plan gives
 * (Part 2.3, B1): Overview, Access, Grants, Sign-ins, Placements and History.
 *
 * **The addresses.** `/people/{id}` is the Overview; `/people/{id}/{view}` is each other view. An
 * address naming a view that does not exist opens the Overview and says nothing, so an address typed
 * to probe learns nothing. A link saved from the old screen carries `principal:{id}` and still opens
 * the person.
 *
 * **One refusal for a person out of reach and a person who is not there.** The page asks
 * `GET /govern/directory/{id}`, which answers both with the same 404, and the page draws the API's
 * sentence and its reference and nothing of its own: a sentence here that differed between the two
 * would be the oracle the route is written not to be.
 *
 * **Each view asks for its own.** The header and the Grants and Placements views are the person's
 * answer; the Access view adds the Roles screen's holders and, for the reader's own page, `/me`;
 * Sign-ins asks the Sessions and Sign-in links screens' own routes filtered to this person; History
 * asks the audit trail about this person. Each of those routes decides for itself what this reader
 * may see, so a view the reader may not read draws that route's own refusal in its place.
 *
 * **Disabling and reinstating are confirmed, in the API's words**, through the same two routes the
 * Departments screen uses (`brain.principal_state_routes`), which ask `may_disable` about the row
 * whatever this page drew, and refuse anybody disabling themselves in their own sentence.
 *
 * Removed from the old page: the principal id in the heading (it is in Advanced), the capability
 * strings as a bare list with no scope, grantor or lapse, and the grant and pack forms drawn open
 * under every person; they are one press away on the Grants view now.
 *
 * Task ids: M27.11.2, M27.11.3, M27.15.18, M27.16.1
 */

import { History, KeyRound, LayoutDashboard, LogIn, Network, ShieldCheck, UserCheck, UserX } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
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
import { dayWords } from "../access/formParts";
import { KindPill, StandingPill } from "./pills";
import { PersonAccess } from "./PersonAccess";
import { PersonGrants } from "./PersonGrants";
import { PersonHistory } from "./PersonHistory";
import { PersonOverview } from "./PersonOverview";
import { PersonPlacements } from "./PersonPlacements";
import { PersonSessions } from "./PersonSessions";
import {
  DISABLE_API_PATH,
  ENABLE_API_PATH,
  PEOPLE_ADDRESS,
  PERSON_VIEWS,
  PERSON_VIEW_LABELS,
  personAddress,
  personApiPath,
  readPersonDetail,
  type PersonDetail,
  type PersonView,
} from "./peopleQuery";
import { PEOPLE_HEADING } from "./PeoplePage";

export const VIEWS_LABEL = "Person views";
export const LOADING_PERSON = "Loading this person.";
export const FIGURES_LABEL = "This person at a glance";
export const DISABLE_LABEL = "Disable sign-in";
export const REINSTATE_LABEL = "Reinstate sign-in";

const VIEW_ICONS: Readonly<Record<PersonView, typeof LayoutDashboard>> = {
  overview: LayoutDashboard,
  access: ShieldCheck,
  grants: KeyRound,
  sessions: LogIn,
  placements: Network,
  history: History,
};

export function stateQuestion(name: string, disable: boolean): string {
  return disable ? `Disable ${name}'s sign-in?` : `Reinstate ${name}'s sign-in?`;
}

/** The control that disables or reinstates a person, confirmed, in the API's words. */
function StandingControl({ detail, onWritten }: { readonly detail: PersonDetail; readonly onWritten: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const disable = detail.person.standing !== "disabled";

  const press = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(disable ? DISABLE_API_PATH : ENABLE_API_PATH, {
        method: "POST",
        body: { principal_id: detail.person.principalId },
      });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onWritten();
    })();
  }, [disable, detail.person.principalId, onWritten]);

  if (!detail.mayDisable) {
    return null;
  }
  const verb = disable ? DISABLE_LABEL : REINSTATE_LABEL;
  const Icon = disable ? UserX : UserCheck;
  return (
    <>
      <Button
        variant={disable ? "outline" : "default"}
        size="sm"
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setFailure(null);
          setAsking(true);
        }}
      >
        <Icon aria-hidden /> {verb}
      </Button>
      {failure === null ? null : (
        <div className="basis-full">
          <FailureState failure={failure} />
        </div>
      )}
      <ConfirmDialog
        open={asking}
        question={stateQuestion(detail.person.displayName, disable)}
        consequence={
          disable
            ? (detail.disabling ?? "Their sessions end and what they hold counts for nothing until they are reinstated. Nothing is deleted.")
            : "They can sign in again, and what they hold counts again from their next request."
        }
        confirmLabel={verb}
        cancelLabel="Leave it as it is"
        busy={busy}
        onConfirm={press}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}

function Figures({ detail }: { readonly detail: PersonDetail }) {
  const { person, placements } = detail;
  const figures = [
    <StatCard
      key="department"
      label="Department"
      value={placements.department?.name ?? person.departmentName ?? person.department ?? "Not placed"}
      sub={placements.teams.length === 0 ? undefined : placements.teams.map((one) => one.name).join(", ")}
    />,
  ];
  // A figure the API did not send is left out, whatever the reason it was not sent.
  if (person.lastSignedInAt !== undefined) {
    figures.push(<StatCard key="last" label="Last sign-in" value={dayWords(person.lastSignedInAt)} />);
  }
  if (person.secondFactor !== undefined) {
    figures.push(
      <StatCard key="second" label="Second factor" value={person.secondFactor ? "Seen" : "Not seen"} sub="in their last sign-in" />,
    );
  }
  if (person.packs.length > 0) {
    figures.push(<StatCard key="packs" label="Packs" value={person.packs.join(", ")} />);
  }
  return (
    <KpiStrip label={FIGURES_LABEL} count={figures.length}>
      {figures}
    </KpiStrip>
  );
}

function PersonAnswer({ principalId, view }: { readonly principalId: string; readonly view: PersonView }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(personApiPath(principalId), version);
  const detail = useMemo(() => readPersonDetail(answer.data), [answer.data]);
  const onWritten = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  // Add work email's sentence, kept here because the overview is drawn again after the reload.
  const [told, setTold] = useState("");
  const onWorkEmail = useCallback(
    (sentence: string, written: boolean) => {
      setTold(sentence);
      if (written) {
        onWritten();
      }
    },
    [onWritten],
  );

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={LOADING_PERSON} />;
  }
  if (detail === null) {
    return null;
  }
  const { person } = detail;
  const headingId = "person-heading";
  const views: DetailView[] = PERSON_VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: PERSON_VIEW_LABELS[one], to: personAddress(principalId, one), icon: <Icon aria-hidden /> };
  });
  const subline = [
    person.departmentName ?? person.department,
    person.employment === undefined ? undefined : person.employment,
  ]
    .filter((one): one is string => one !== undefined)
    .join(" · ");

  return (
    <DetailPage
      crumbs={[{ label: PEOPLE_HEADING, to: PEOPLE_ADDRESS }, { label: person.displayName }]}
      header={
        <DetailHeader
          name={person.displayName}
          headingId={headingId}
          pills={
            <>
              <StandingPill standing={person.standing} />
              {person.employment === undefined || person.employment === "staff" ? null : <KindPill>{person.employment}</KindPill>}
            </>
          }
          subline={subline === "" ? undefined : subline}
          actions={<StandingControl detail={detail} onWritten={onWritten} />}
          figures={<Figures detail={detail} />}
        />
      }
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
    >
      {view === "overview" ? <PersonOverview detail={detail} told={told} onWorkEmail={onWorkEmail} /> : null}
      {view === "access" ? <PersonAccess detail={detail} /> : null}
      {view === "grants" ? <PersonGrants detail={detail} onWritten={onWritten} /> : null}
      {view === "sessions" ? <PersonSessions detail={detail} /> : null}
      {view === "placements" ? <PersonPlacements detail={detail} onWritten={onWritten} /> : null}
      {view === "history" ? <PersonHistory detail={detail} /> : null}
    </DetailPage>
  );
}

export function PersonDetailPage({ principalId, view }: { readonly principalId: string; readonly view: PersonView }) {
  return (
    <div data-slot="person-page" className="min-w-0">
      <PersonAnswer key={principalId} principalId={principalId} view={view} />
    </div>
  );
}

