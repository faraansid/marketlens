import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { LineChart, Rocket, Users, type LucideIcon } from "lucide-react";

/**
 * Dashboard module registry. Each entry becomes a sidebar item and a route
 * under /app. Adding a module (e.g. "Watchlists", "Sectors") is one entry here
 * plus its page component — no layout or router restructuring needed.
 */
export interface AppModule {
  path: string; // relative to /app
  label: string;
  icon: LucideIcon;
  description: string;
  component: LazyExoticComponent<ComponentType>;
  /** Only visible/routable for the owner account (the API enforces this too). */
  ownerOnly?: boolean;
  section?: "Analysis" | "Administration";
}

export const MODULES: AppModule[] = [
  {
    path: "market",
    label: "Market",
    icon: LineChart,
    description: "Indices, macro instruments and the full equity screener",
    component: lazy(() => import("../pages/MarketPage")),
  },
  {
    path: "breakouts",
    label: "Breakouts",
    icon: Rocket,
    description: "VCP, falling wedges, breakouts and trend scans",
    component: lazy(() => import("../pages/BreakoutsPage")),
  },
  {
    path: "users",
    label: "Users",
    icon: Users,
    description: "Add and manage who can sign in",
    component: lazy(() => import("../pages/UsersPage")),
    ownerOnly: true,
    section: "Administration",
  },
];

export function modulesFor(isOwner: boolean): AppModule[] {
  return MODULES.filter((m) => !m.ownerOnly || isOwner);
}
