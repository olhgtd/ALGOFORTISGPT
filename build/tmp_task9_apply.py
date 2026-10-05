from pathlib import Path

path = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
text = path.read_text(encoding="utf-8")

text = text.replace("  OwnerAccessRegistryScreen,\n", "", 1)
text = text.replace('import { OwnerUsersInspectionScreen } from "./authoritative/UserInspection";\n', '', 1)
text = text.replace('import { SystemOperations } from "./authoritative/SystemOperations";\n', 'import { SystemOperations } from "./authoritative/SystemOperations";\nimport { UsersAccessScreen } from "./authoritative/UsersAccessScreen";\n', 1)

start = text.index('export const DESKTOP_OWNER_NAV_GROUPS: NavGroup[] = [')
end = text.index('\n];\n\nexport const MOBILE_OWNER_NAV', start) + len('\n];')
nav = '''export const DESKTOP_OWNER_NAV_GROUPS: NavGroup[] = [
  {
    label: "CONTROL",
    items: [
      { id: "control", label: "Overview", icon: "home", badge: "Root", badgeTone: "warn" },
      { id: "users", label: "Users & Access", icon: "users" },
      { id: "strategies", label: "Strategies", icon: "code" },
      { id: "plugins", label: "Connections & Data", icon: "plug" },
    ],
  },
  {
    label: "RESEARCH & OPERATIONS",
    items: [
      { id: "research", label: "Backtests / Walk-Forward", icon: "play" },
      { id: "paper", label: "Paper Trading", icon: "layers" },
      { id: "deployments", label: "Deployments", icon: "activity" },
      { id: "portfolio-oversight", label: "Portfolio & Orders", icon: "chart" },
      { id: "reports", label: "Reports & Audit", icon: "file" },
    ],
  },
  {
    label: "SAFETY & INTELLIGENCE",
    items: [
      { id: "risk-safety", label: "Risk & Safety", icon: "shield", badge: "Live disarmed", badgeTone: "warn" },
      { id: "ai-control", label: "AI Control Center", icon: "activity", badge: "Decision Intel", badgeTone: "dim" },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { id: "product-operations", label: "Product Operations", icon: "activity", badge: "Read only", badgeTone: "dim" },
      { id: "system", label: "System Health", icon: "activity" },
      { id: "security", label: "Security Authority", icon: "shield" },
      { id: "incidents", label: "Security Incidents", icon: "file" },
      { id: "settings", label: "Settings", icon: "shield" },
    ],
  },
];'''
text = text[:start] + nav + text[end:]

mstart = text.index('export const MOBILE_OWNER_NAV: NavItem[] = [')
mend = text.index('\n];\n\nconst ALL_SCREEN_IDS', mstart) + len('\n];')
mobile = '''export const MOBILE_OWNER_NAV: NavItem[] = [
  { id: "control", label: "Overview", icon: "home" },
  { id: "users", label: "Users & Access", icon: "users" },
  { id: "research", label: "Research", icon: "play" },
  { id: "risk-safety", label: "Safety", icon: "shield" },
  { id: "more", label: "More", icon: "more" },
];'''
text = text[:mstart] + mobile + text[mend:]

old_ids = 'const ALL_SCREEN_IDS = DESKTOP_OWNER_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id));'
new_ids = '''const LEGACY_SCREEN_ALIASES: Record<string, string> = { "access-registry": "users" };
const ALL_SCREEN_IDS = DESKTOP_OWNER_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id));
const canonicalScreenId = (id: string) => LEGACY_SCREEN_ALIASES[id] || id;'''
if old_ids not in text: raise SystemExit('ALL_SCREEN_IDS anchor missing')
text = text.replace(old_ids, new_ids, 1)

old_initial = '''    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    return ALL_SCREEN_IDS.includes(hash) ? hash : "control";'''
new_initial = '''    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    const canonical = canonicalScreenId(hash);
    return ALL_SCREEN_IDS.includes(canonical) ? canonical : "control";'''
if old_initial not in text: raise SystemExit('initial hash anchor missing')
text = text.replace(old_initial, new_initial, 1)

old_hash = '''      const hash = window.location.hash.replace(/^#/, "");
      if (ALL_SCREEN_IDS.includes(hash)) setScreen(hash);'''
new_hash = '''      const hash = canonicalScreenId(window.location.hash.replace(/^#/, ""));
      if (ALL_SCREEN_IDS.includes(hash)) setScreen(hash);'''
if old_hash not in text: raise SystemExit('hash handler anchor missing')
text = text.replace(old_hash, new_hash, 1)

old_go = '''    if (id === "more") { setMoreOpen((open) => !open); return; }
    if (!ALL_SCREEN_IDS.includes(id)) return;
    setScreen(id);
    setMoreOpen(false);
    if (typeof window !== "undefined") {
      window.location.hash = `#${id}`;'''
new_go = '''    if (id === "more") { setMoreOpen((open) => !open); return; }
    const canonical = canonicalScreenId(id);
    if (!ALL_SCREEN_IDS.includes(canonical)) return;
    setScreen(canonical);
    setMoreOpen(false);
    if (typeof window !== "undefined") {
      window.location.hash = `#${canonical}`;'''
if old_go not in text: raise SystemExit('go anchor missing')
text = text.replace(old_go, new_go, 1)

text = text.replace('      case "users": return <OwnerUsersInspectionScreen />;\n      case "access-registry": return <OwnerAccessRegistryScreen />;\n', '      case "users": return <UsersAccessScreen />;\n', 1)
text = text.replace('["control", "portfolio-oversight", "ai-control", "users", "product-operations", "research"].includes(screen)', '["control", "portfolio-oversight", "ai-control", "users", "product-operations", "research", "paper", "deployments", "plugins", "risk-safety", "system"].includes(screen)', 1)

path.write_text(text, encoding="utf-8")
