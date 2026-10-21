/**
 * The control on Ask that chooses a personal project to ask inside (M40.7.7).
 *
 * **Offered only when the person has a project.** A person with none, or whose install has the
 * switch off and no project made, sees no control rather than a dead one. The list is the API's
 * own (`GET /me/projects`), which answers for the person asking alone.
 *
 * **Choosing a project sends its id beside the question and decides nothing.** The route reads the
 * project's documents at the reach the run holds, so a document the person can no longer read is
 * left out of the answer without a word, and nothing here marks it. The control says what asking
 * inside a project does and does not do: its documents are read for the answer and are not kept as
 * memory.
 *
 * Task ids: M40.7.7
 */

import { useEffect, useState } from "react";
import { request } from "../api/client";
import { PROJECTS_API_PATH, type ProjectsBody } from "./myProjectsQuery";

export const PROJECT_LABEL = "Ask inside a project";
export const NO_PROJECT = "No project";
export const PROJECT_NOTE =
  "The project's documents are read for this answer, at the access you hold now, and are never " +
  "kept as memory. This conversation is added to the project.";

const PROJECT_FIELD_ID = "ask-project";

export function AskProject({
  project,
  disabled,
  onChange,
}: {
  readonly project: string;
  readonly disabled: boolean;
  readonly onChange: (project: string) => void;
}): React.JSX.Element | null {
  const [listed, setListed] = useState<ProjectsBody | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const answered = await request<ProjectsBody>(PROJECTS_API_PATH);
      if (live && answered.ok) {
        setListed(answered.data);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  if (listed === null || listed.projects.length === 0) {
    return null;
  }
  return (
    <>
      <label className="ask__label" htmlFor={PROJECT_FIELD_ID}>
        {PROJECT_LABEL}
      </label>
      <select
        id={PROJECT_FIELD_ID}
        className="form-control"
        value={project}
        disabled={disabled}
        aria-describedby={`${PROJECT_FIELD_ID}-note`}
        onChange={(changed) => onChange(changed.target.value)}
      >
        <option value="">{NO_PROJECT}</option>
        {listed.projects.map((one) => (
          <option key={one.project_id} value={one.project_id}>
            {one.name}
          </option>
        ))}
      </select>
      <p id={`${PROJECT_FIELD_ID}-note`} className="note">
        {PROJECT_NOTE}
      </p>
    </>
  );
}
