/**
 * People, at the addresses the route table and the menu use: `/people` is the list and
 * `/people/{id}` and `/people/{id}/{view}` are one person's page. Both are built on the shared page
 * kit in `people/`; this module keeps the name the route file loads.
 *
 * The old screen listed grant holders by subject key and resolved a subject against its own page.
 * It is replaced by the directory of every person and a page per person, whose route answers a
 * person out of reach exactly as a person who is not there (`brain.directory_routes`).
 *
 * Task ids: M27.11.2, M27.16.1
 */

import { useParams } from "react-router-dom";
import { PeoplePage } from "./people/PeoplePage";
import { PersonDetailPage } from "./people/PersonDetailPage";
import { principalFromAddress, viewNamed } from "./people/peopleQuery";

export { PEOPLE_HEADING, PEOPLE_LEDE, NO_PEOPLE } from "./people/PeoplePage";

export function People() {
  const { personId, view } = useParams();
  if (personId === undefined) {
    return <PeoplePage />;
  }
  const principalId = principalFromAddress(personId);
  return <PersonDetailPage key={principalId} principalId={principalId} view={viewNamed(view)} />;
}
