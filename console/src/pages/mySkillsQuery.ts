/**
 * What the skills card in My workspace asks the API for and what it sends. No React.
 *
 * `brain.member_skill_routes` answers for the person asking and nobody else and takes no parameter
 * naming a person. A skill is written, pasted or brought from an address or a repository, kept as
 * the person's own, and offered to the department's library; nothing here approves anything.
 *
 * Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3
 */

import type { components } from "../api/schema";

export type MySkillsBody = components["schemas"]["PersonalSkillsView"];
export type MySkill = components["schemas"]["PersonalSkillView"];

export const MY_SKILLS_API_PATH = "/me/skills";
export const IMPORT_MY_SKILL_API_PATH = "/me/skills/imports";

/** Where one of the person's own skills is offered to the department, under the API base. */
export function offerMySkillApiPath(digest: string): string {
  return `/me/skills/${encodeURIComponent(digest)}/offer`;
}

/** The three ways a person brings a skill in. */
export type Way = "write" | "address" | "repository";

export const WAYS: readonly { readonly way: Way; readonly label: string }[] = [
  { way: "write", label: "Write or paste it here" },
  { way: "address", label: "Bring it from an address" },
  { way: "repository", label: "Bring it from a repository" },
];

/** What a person has typed, as a form holds it. */
export interface SkillDraft {
  readonly way: Way;
  readonly text: string;
  readonly url: string;
  readonly repository: string;
  readonly commit: string;
  readonly path: string;
}

export const EMPTY_DRAFT: SkillDraft = {
  way: "write",
  text: "",
  url: "",
  repository: "",
  commit: "",
  path: "",
};

/** What a blank draft is told, in the order the fields come, or an empty string when it can be sent. */
export function whatToFill(draft: SkillDraft): string {
  switch (draft.way) {
    case "write":
      return draft.text.trim() === "" ? "Write or paste the skill's SKILL.md before adding it." : "";
    case "address":
      return draft.url.trim() === "" ? "Give the https address the skill is fetched from." : "";
    case "repository":
      return draft.repository.trim() === "" || draft.commit.trim() === ""
        ? "Give the repository as owner/name and the full commit the skill is pinned to."
        : "";
    default:
      // A select emptied by the browser, or a value this build does not know, sends nothing.
      return "Choose how the skill is brought in before adding it.";
  }
}

/** The body a written or pasted skill sends. */
export function writeBody(draft: SkillDraft): {
  readonly file_name: string;
  readonly content: string;
  readonly encoding: "text";
} {
  return { file_name: "SKILL.md", content: draft.text, encoding: "text" };
}

/** The body a skill brought from an address or a repository sends. */
export function importBody(draft: SkillDraft): {
  readonly kind: "github" | "url";
  readonly repository: string;
  readonly commit: string;
  readonly path: string;
  readonly url: string;
} {
  return draft.way === "repository"
    ? {
        kind: "github",
        repository: draft.repository.trim(),
        commit: draft.commit.trim(),
        path: draft.path.trim(),
        url: "",
      }
    : { kind: "url", repository: "", commit: "", path: "", url: draft.url.trim() };
}
