/**
 * Which source to connect first, on the Connectors list while nothing is connected (M34.1.1.1).
 *
 * The API picks it (`brain.adoption.first_connector`, through `GET /console/connector-start`): a
 * source whose records already exist and can be opened in their own system, so a real question is
 * answerable before any document is uploaded, and the widest one where several would do. This line
 * only says so. It is drawn while no source is connected and not afterwards, because a suggestion
 * about where to start is wrong the moment somebody has, and it is absent when the API suggests none,
 * where saying nothing is better than recommending a week of uploading files.
 *
 * Task ids: M34.1.1.1
 */

import { useResource } from "../../api/useResource";
import { Note } from "../../components/kit";
import { readStart, START_API_PATH } from "../adoptionCoverageQuery";

/** Before the source's name. */
export const START_WITH = "Start with";

/** After it: why that one. */
export const START_BECAUSE =
  "Its records already exist and can be opened in their own system, so a real question can be answered, and checked, before any document is uploaded.";

export function ConnectorStart({ connectedAny }: { readonly connectedAny: boolean }) {
  const answer = useResource<unknown>(connectedAny ? null : START_API_PATH);
  if (connectedAny || answer.busy || answer.failure !== null) {
    return null;
  }
  const start = readStart(answer.data);
  if (start === undefined) {
    return null;
  }
  return (
    <div role="status">
      <Note kind="info">
        {START_WITH} {start.label}. {START_BECAUSE}
      </Note>
    </div>
  );
}
