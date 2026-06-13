/* App-Shell: Hash-Router, Navigation nach Berechtigungen, Auth-Gate. */

import { api, getToken, clearToken } from "./api.js";
import { registerAuthPages } from "./pages/auth.js";
import { registerCorePages } from "./pages/core.js";
import { registerModulePages } from "./pages/modules.js";
import { registerAdminPages } from "./pages/admin.js";
import { registerBuilderPages, ensureCustomModules } from "./pages/builder.js";
import registerWorkflowPages from "./pages/workflows.js";

export const state = { me: null, setupStatus: null };

/* Seiten-Registry: spätere Etappen (Builder, Workflows …) registrieren
   hier einfach weitere Seiten. */
const pages = new Map();
export function registerPage(route, page) { pages.set(route, page); }
export function navigate(route) { location.hash = `#/${route}`; }

export function hasPermission(module, action = "read") {
  if (!state.me) return false;
  return state.me.permissions.some(
    (p) => (p.module === "*" || p.module === module) && (p.action === "write" || action === "read"),
  );
}

const main = document.getElementById("main");
const nav = document.getElementById("nav");
const header = document.getElementById("header");

function renderNav(active) {
  nav.innerHTML = "";
  for (const [route, page] of pages) {
    if (!page.nav) continue;
    if (page.module && !hasPermission(page.module)) continue;
    const link = document.createElement("a");
    link.href = `#/${route}`;
    link.textContent = page.title;
    if (route === active) link.classList.add("active");
    nav.append(link);
  }
}

async function refreshHeaderStatus() {
  try {
    const status = await api("/api/ai/status");
    document.getElementById("ai-status").textContent = status.llm_available
      ? `KI aktiv · ${status.indexed_chunks} Chunks`
      : `KI offline · ${status.indexed_chunks} Chunks`;
  } catch { /* z. B. keine ai-Berechtigung */ }
}

export async function loadMe() {
  state.me = await api("/api/auth/me");
  document.getElementById("company").textContent = state.me.tenant.name;
  document.getElementById("who").textContent = `${state.me.display_name} (${state.me.role})`;
  refreshHeaderStatus();
  await ensureCustomModules(); // dynamische Seiten der Custom-Module registrieren
}

// Re-Entrancy-Schutz: zwei schnell aufeinanderfolgende Aufrufe (z. B. nach
// einem Hash-Wechsel) dürfen sich nicht ins Gehege kommen und doppelt rendern.
let routeToken = 0;

async function route() {
  const token = ++routeToken;
  const path = (location.hash.replace(/^#\//, "") || "dashboard").split("?")[0];
  const [routeName] = path.split("/");
  const page = pages.get(routeName) || pages.get("dashboard");

  const isPublic = page.public === true;
  if (!isPublic) {
    if (!getToken()) { location.hash = "#/login"; return; }
    if (!state.me) {
      try { await loadMe(); }
      catch { clearToken(); location.hash = "#/login"; return; }
      if (token !== routeToken) return; // während loadMe kam ein neuer route()
    }
    header.style.display = "";
    nav.style.display = "";
    renderNav(routeName);
  } else {
    header.style.display = "none";
    nav.style.display = "none";
  }

  main.innerHTML = "";
  try {
    await page.render(main, path.split("/").slice(1));
  } catch (err) {
    if (token === routeToken) main.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

document.getElementById("logout").addEventListener("click", () => {
  clearToken(); state.me = null; location.hash = "#/login";
});

registerAuthPages();
registerCorePages();
registerModulePages();
registerBuilderPages();
registerWorkflowPages();
registerAdminPages();

window.addEventListener("hashchange", route);

// Boot: Erstinstallation → Setup-Wizard.
// Wichtig: Wenn wir den Hash ändern, übernimmt das hashchange-Event den
// route()-Aufruf — sonst rendern wir doppelt. Nur ohne Hash-Wechsel selbst routen.
state.setupStatus = await api("/api/setup/status").catch(() => null);
if (state.setupStatus?.needs_setup && !location.hash.startsWith("#/setup")) {
  location.hash = "#/setup"; // löst hashchange → route() aus
} else {
  route();
}
