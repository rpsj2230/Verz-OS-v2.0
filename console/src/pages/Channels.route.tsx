/**
 * Channels, E1 of Channels and notifications: each chat surface's set-up, switch, health from its
 * deliveries and the people bound on it. No registry key: the page cites
 * `brain.console.channel_health` instead. A person's own chats are a card in My workspace,
 * `components/MyChannels.tsx`, and need no route of their own.
 *
 * Task ids: M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import type { PageRoutes } from "../routes/page";
import { Channels } from "./Channels";

export const routes: PageRoutes = [{ path: "channels", element: <Channels /> }];
