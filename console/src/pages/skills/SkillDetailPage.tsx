/**
 * One skill's page on the shared kit, in SCREEN 14's shape: one header and its figures, shared by
 * three views in the owner's order, Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/skills/{name}` is the Dashboard, because it opens first; `/skills/{name}/profile`
 * and `/skills/{name}/about` are the other two. An address naming anything else opens the Dashboard
 * silently, so an address typed to probe learns nothing.
 *
 * **One request for the page, and each view asks only for its own.** The Skills page's answer,
 * narrowed to the name, fills the header and the Profile; the Dashboard asks the stats route; the
 * About view asks the audit ledger. After a write the page's answer is asked for again under a new
 * version, so the header, the versions and the agents are what the API holds after it.
 *
 * **A skill nobody here may see and a skill that does not exist are one sentence.** The page's
 * answer is filtered by the API to what this reader may see, and an empty answer draws the same
 * empty state whichever it is.
 *
 * **What was removed from the old page, and why.** The digest printed under every version and the
 * principal id of whoever added and decided it (identifiers, now in each version's Advanced); the
 * library and the review queue drawn again under the open skill; the add and import forms drawn on a
 * page about one skill; and the paragraph about reach under every version, now one sentence above
 * them.
 *
 * Task ids: M27.16.1, M27.11.8, M27.15.55, M27.15.56
 */

import { IdCard, Info, LayoutDashboard } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  Chip,
  DetailHeader,
  DetailPage,
  EmptyState,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  PageHeader,
  StatCard,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { skillAddress } from "../skillsQuery";
import { ReviewPill, RetiredPill } from "./pills";
import { SkillAbout } from "./SkillAbout";
import { SkillDashboard } from "./SkillDashboard";
import { sourceWord } from "./skillActions";
import {
  dayWords,
  headlineVersion,
  readSkillDetail,
  skillApiPath,
  viewFor,
  VIEW_LABELS,
  VIEWS,
  type SkillView,
} from "./skillDetailQuery";
import type { Told } from "./SkillForms";
import { SkillProfile } from "./SkillProfile";
import { SKILLS_HEADING } from "./SkillsPage";

export const VIEWS_LABEL = "Skill views";
export const LOADING_SKILL = "Loading this skill.";
export const NO_SUCH_SKILL = "No skill to show";
export const NO_SUCH_SKILL_DESCRIPTION = "Nothing in the library you can see has that name.";
export const HEADER_FIGURES = "This skill at a glance";

const VIEW_ICONS: Readonly<Record<SkillView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** Where a view of a skill is. The Dashboard is the bare address. */
export function skillViewAddress(name: string, view: SkillView): string {
  return view === VIEWS[0] ? skillAddress(name) : `${skillAddress(name)}/${view}`;
}

function SkillAnswer({ name, view: asked }: { readonly name: string; readonly view: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);
  const answer = useResource<unknown>(skillApiPath(name), version);
  const detail = useMemo(() => (answer.data === null ? null : readSkillDetail(answer.data, name)), [answer.data, name]);
  const onTold = useCallback((next: Told) => {
    setTold(next);
    if (next.ok) {
      setVersion((one) => one + 1);
    }
  }, []);
  const view = viewFor(asked);
  const crumbs = [{ label: SKILLS_HEADING, to: "/skills" }, { label: name }];

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy && answer.data === null) {
    return <LoadingState label={LOADING_SKILL} />;
  }
  if (detail === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={crumbs} title={name} />
        <EmptyState title={NO_SUCH_SKILL} description={NO_SUCH_SKILL_DESCRIPTION} />
      </div>
    );
  }
  const headline = headlineVersion(detail);
  const agentsRunning = new Set((detail.pinned?.pinned_by ?? []).map((one) => one.agent_id)).size;
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: skillViewAddress(name, one), icon: <Icon aria-hidden /> };
  });
  const profileAddress = skillViewAddress(name, "profile");

  const header = (
    <DetailHeader
      name={name}
      headingId={`skill-${name}`}
      pills={
        headline === undefined ? undefined : (
          <>
            <ReviewPill review={headline.review} />
            {headline.retired === true ? <RetiredPill /> : null}
          </>
        )
      }
      subline={headline === undefined ? undefined : `version ${headline.version}`}
      actions={
        headline === undefined || headline.categories.length === 0 ? undefined : (
          <span className="flex flex-wrap gap-1">
            {headline.categories.map((one) => (
              <Chip key={one}>{one}</Chip>
            ))}
          </span>
        )
      }
      figures={
        <KpiStrip label={HEADER_FIGURES} count={3}>
          <StatCard label="Newest version" value={headline?.version} />
          <StatCard label="Added" value={dayWords(headline?.submitted_at)} sub={headline === undefined ? undefined : sourceWord(headline.source)} />
          <StatCard label="Agents using it" value={String(agentsRunning)} sub="among the agents you can see" />
        </KpiStrip>
      }
    />
  );

  return (
    <DetailPage crumbs={crumbs} header={header} switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}>
      <div className="flex min-w-0 flex-col gap-3">
        {told === null ? null : (
          <div role={told.ok ? "status" : "alert"}>
            <Note kind={told.ok ? "done" : "info"}>{told.sentence}</Note>
          </div>
        )}
        {view === "dashboard" ? <SkillDashboard detail={detail} profileAddress={profileAddress} /> : null}
        {view === "profile" ? <SkillProfile detail={detail} onTold={onTold} /> : null}
        {view === "about" ? <SkillAbout detail={detail} profileAddress={profileAddress} /> : null}
      </div>
    </DetailPage>
  );
}

export function SkillDetailPage({ name, view }: { readonly name: string; readonly view: string | undefined }) {
  return (
    <div data-slot="skill-page" className="min-w-0">
      <SkillAnswer key={name} name={name} view={view} />
    </div>
  );
}
