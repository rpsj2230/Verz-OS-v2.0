/**
 * The template catalogue: the roles somebody can install, which is `docs/screens.html`
 * SCREEN 5.
 *
 * **It exists because the owner opened his own install and could not find it.** The
 * twenty-three manifests in `brain.agents.catalogue` have been in this repository since M13.5
 * and nothing in a browser had ever shown one, so a person looking for "what agents can I
 * start from" had the source tree and nothing else.
 *
 * **Nothing on this page decides who may read it.** The API answers it behind the Skills and
 * templates screen's own read and refuses everybody else in that screen's words, which this
 * page renders as it renders any other refusal: the sentence and the trace id, with no list
 * drawn over it and no explanation composed here.
 *
 * **The design's card has three things this one does not.** An install control, an install
 * count, and a department. The first two are argued in `agentTemplatesQuery.ts`; the third is
 * absent because a template has no audience of its own until it is installed, so the
 * department on SCREEN 5's card is a fact about the agents somebody made from it, and a
 * department drawn here would be a claim about rows this reader may not be able to open.
 *
 * Imported statically rather than split, which is `App.tsx`'s rule for `Overview` and
 * `Agents`: it mounts neither heavy library and imports no stylesheet of its own, so a chunk
 * for it would buy a round trip and save no bytes.
 *
 * Task ids: M27.8.6
 */

import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows, type FilterChoice, type SortChoice } from "../components/listing";
import { useListing } from "../components/useListing";
import type { components } from "../api/schema";
import { readTemplates, TEMPLATES_API_PATH } from "./agentTemplatesQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's heading, in the design's own words. */
export const TEMPLATES_HEADING = "Agent Templates";

/** Under it. SCREEN 5's own sentence about what a template is. */
export const TEMPLATES_LEDE =
  "A template is a role someone can install: prompt, skills, connectors and a starting leash, " +
  "versioned together.";

/** The design's closing sentence, which is the one a person installing a role needs most. */
export const INSTALLING_NEVER_WIDENS =
  "Installing never widens anyone. A template asks for tools; the department admin decides " +
  "whether the grant exists, and a run is still bounded by whoever called it.";

/**
 * SCREEN 5's panel saying what a template carries, row for row in its own words.
 *
 * Static, because it is a fact about `brain.agents.template.TemplateManifest` and not about
 * any row: the persona and identity are versioned together, skills are `SkillRef`s pinned by
 * digest, tools are the authority section's ceiling rather than a grant, connectors are a
 * declaration of readiness, the leash is sealed, and the golden set travels with the manifest.
 * Each line was checked against that module before it was written here.
 */
export const WHAT_A_TEMPLATE_CARRIES_HEADING = "What a template carries";
export const WHAT_A_TEMPLATE_CARRIES: readonly (readonly [string, string])[] = Object.freeze([
  ["System prompt and role", "versioned"],
  ["Skills", "by reference, pinned"],
  ["Tools requested", "a request, not a grant"],
  ["Connectors expected", "named, may be absent"],
  ["Default leash", "shadow on every write"],
  ["Evaluation set", "ships with the template"],
]);

/**
 * Said under the panel, because the leash line is true of every template this product ships
 * and is not a promise about one this installation published: its leash is whatever its author
 * sealed, and the panel must not read as a guarantee the manifest does not make.
 */
export const THE_LEASH_LINE_IS_THE_CATALOGUES =
  "Every template that ships with this product starts on shadow. A template published here " +
  "carries the leash its author sealed into it.";

/** An empty catalogue, whichever of the reasons it is empty. */
export const NO_TEMPLATES = "There are no templates to show.";

/** A truncated catalogue. A fact about there being more, and never a figure. */
export const MORE_TEMPLATES = "There are more templates than this page shows.";

/** The accessible name of the list. */
export const TEMPLATES_LIST_LABEL = "Templates you can install from";

/** The word before a version number, as the agent header spells it. */
export const VERSION_WORD = "version";

/** What is said where an install control would be. */
export const INSTALLING_IS_NOT_OFFERED_HERE =
  "Installing is not offered in this console yet. A template is installed by the setup " +
  "path, which signs the manifest and asks for the values this company has to supply.";

/**
 * The two words for an origin.
 *
 * A table of two rather than the member rendered raw, because "built_in" is a key and the
 * distinction it carries is the one a person choosing a role needs in words. An origin that is
 * neither renders as itself, which is `src/ui/Status.tsx`'s rule for an unknown state word.
 */
const ORIGIN_WORDS: Readonly<Record<string, string>> = Object.freeze({
  built_in: "ships with this product",
  published: "published here",
});

export function originWords(origin: string): string {
  return ORIGIN_WORDS[origin] ?? origin;
}

export const FILTERS_LABEL = "Narrow the templates";
export const NONE_MATCH = NOTHING_MATCHES;

type TemplateRow = components["schemas"]["TemplateEntry"];

/** The filters the gallery route declares that this screen offers, over values on cards drawn. */
export const TEMPLATE_FILTERS: readonly FilterChoice<TemplateRow>[] = [
  {
    column: "origin",
    label: "Where it came from",
    everything: "Shipped or published",
    read: (row) => row.origin,
    describe: (value) => originWords(value),
  },
  { column: "published_by", label: "Published by", everything: "Anybody", read: (row) => row.published_by },
];

export const TEMPLATE_SORTS: readonly SortChoice[] = [
  { value: "", label: "By name" },
  { value: "template_id", label: "By id" },
  { value: "-version", label: "Newest version first" },
];

function TemplatesAnswerView() {
  const listing = useListing<TemplateRow>(TEMPLATES_API_PATH, { choices: TEMPLATE_FILTERS });
  const controls = (
    <ListControls label={FILTERS_LABEL} listing={listing} choices={TEMPLATE_FILTERS} sorts={TEMPLATE_SORTS} />
  );

  if (listing.failure) {
    return (
      <>
        {controls}
        <FailureNotice failure={listing.failure} />
      </>
    );
  }
  if (listing.busy) {
    return (
      <>
        {controls}
        <p className="note" role="status">
          Loading.
        </p>
      </>
    );
  }
  const gallery = readTemplates(listing.body);
  if (gallery === null) {
    return controls;
  }
  return (
    <>
      {controls}
      {gallery.cards.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_TEMPLATES}</p>
      ) : (
        <ul className="roster" aria-label={TEMPLATES_LIST_LABEL}>
          {gallery.cards.map((card) => (
            <li key={card.templateId}>
              <h2>
                {card.displayName}{" "}
                <span className="note">
                  {VERSION_WORD} {card.version}
                </span>
              </h2>
              {card.summary === undefined ? null : <p>{card.summary}</p>}
              <p className="note">
                <code>{card.templateId}</code> {originWords(card.origin)}, by{" "}
                <code>{card.publishedBy}</code>
              </p>
            </li>
          ))}
        </ul>
      )}
      <ShowMore listing={listing} />
      {gallery.truncated ? <p className="note">{MORE_TEMPLATES}</p> : null}
      <p className="note">{INSTALLING_IS_NOT_OFFERED_HERE}</p>
    </>
  );
}

export function AgentTemplates() {
  return (
    <article className="page">
      <h1>{TEMPLATES_HEADING}</h1>
      <p className="lede">{TEMPLATES_LEDE}</p>
      <TemplatesAnswerView />
      {/*
       * Outside the answer, because it is product documentation rather than a reading: it is
       * true whether or not this reader may open the catalogue, and it names no template.
       */}
      <section aria-label={WHAT_A_TEMPLATE_CARRIES_HEADING}>
        <h2>{WHAT_A_TEMPLATE_CARRIES_HEADING}</h2>
        <dl className="agent-template-carries">
          {WHAT_A_TEMPLATE_CARRIES.map(([label, value]) => (
            <div className="fields__row" key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <p className="note">{THE_LEASH_LINE_IS_THE_CATALOGUES}</p>
        <p className="note">{INSTALLING_NEVER_WIDENS}</p>
      </section>
    </article>
  );
}
