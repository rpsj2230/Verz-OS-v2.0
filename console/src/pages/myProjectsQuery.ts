/**
 * What the projects card in My workspace asks the API for. No React.
 *
 * `brain.project_routes` answers for the person asking and nobody else, and takes no parameter
 * naming a person. A project is a list of the person's own threads and of documents they may read;
 * it is context for a question asked inside it and is never kept as memory, and the card says so.
 * Nothing here counts anything: a document the person can no longer read stays on the list and
 * nothing marks it, because a mark would say what they may no longer read.
 *
 * Task ids: M40.7.7
 */

import type { components } from "../api/schema";

export type ProjectsBody = components["schemas"]["ProjectsView"];
export type ProjectView = components["schemas"]["ProjectView"];
export type ProjectDetail = components["schemas"]["ProjectDetailView"];
export type ProjectItemView = components["schemas"]["ProjectItemView"];

export const PROJECTS_API_PATH = "/me/projects";

/** Where one project is read, under the API base. */
export function projectApiPath(projectId: string): string {
  return `${PROJECTS_API_PATH}/${encodeURIComponent(projectId)}`;
}

export function renameApiPath(projectId: string): string {
  return `${projectApiPath(projectId)}/rename`;
}

export function archiveApiPath(projectId: string): string {
  return `${projectApiPath(projectId)}/archive`;
}

export function addItemApiPath(projectId: string): string {
  return `${projectApiPath(projectId)}/items`;
}

export function removeItemApiPath(projectId: string): string {
  return `${projectApiPath(projectId)}/items/remove`;
}

/** The longest name the API keeps, held against its own document by a test. */
export const MAX_PROJECT_NAME_CHARS = 120;

/** The body that names a project, or null for a name the API would refuse. */
export function nameBody(name: string): { readonly name: string } | null {
  const kept = name.trim().split(/\s+/).join(" ");
  return kept === "" || kept.length > MAX_PROJECT_NAME_CHARS ? null : { name: kept };
}

/** The body that lists, or takes out, one thread or one file by id. */
export function itemBody(
  kind: "file" | "thread",
  ref: string,
): { readonly kind: "file" | "thread"; readonly ref: string } {
  return { kind, ref };
}

/** The body of `POST /answer` gains the project the question is asked inside, when one is chosen. */
export function projectField(project: string): { readonly project?: string } {
  return project === "" ? {} : { project };
}
