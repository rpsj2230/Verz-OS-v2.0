/**
 * One channel's page, at `/channels/{name}` and `/channels/{name}/{view}`. The page itself is
 * `channels/ChannelDetailPage.tsx`, built on the shared page kit; this module is what the route file
 * loads on demand, so somebody who never opens a channel does not download its forms.
 *
 * Task ids: M27.13.1, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ChannelDetailPage } from "./channels/ChannelDetailPage";

export function Channel() {
  const { name, view } = useParams();
  return name === undefined ? null : <ChannelDetailPage name={name} tab={view} />;
}
