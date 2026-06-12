/* Login und Onboarding-Wizard (Ersteinrichtung in einer Minute). */

import { api, setToken } from "../api.js";
import { el, renderForm } from "../ui.js";
import { registerPage, state, loadMe } from "../app.js";

function authShell(title, ...content) {
  return el("div", { class: "auth-wrap" },
    el("h1", {}, "KMU-", el("em", {}, "OS")),
    el("p", { class: "hint", style: "text-align:center" }, title),
    ...content);
}

export function registerAuthPages() {
  registerPage("login", {
    title: "Anmelden", public: true,
    async render(main) {
      const status = state.setupStatus || await api("/api/setup/status");
      if (status.needs_setup) { location.hash = "#/setup"; return; }
      const form = renderForm({
        fields: [
          { name: "email", label: "E-Mail", type: "email", required: true },
          { name: "password", label: "Passwort", type: "password", required: true },
        ],
        submitLabel: "Anmelden",
        onSubmit: async (data) => {
          const result = await api("/api/auth/login", { method: "POST", body: data });
          setToken(result.access_token);
          state.me = null;
          await loadMe();
          location.hash = "#/dashboard";
        },
      });
      const extras = [];
      if (status.allow_signup) {
        extras.push(el("p", { class: "hint", style: "text-align:center" },
          "Neue Firma? ", el("a", { href: "#/register" }, "Jetzt registrieren")));
      }
      main.append(authShell("Anmeldung zum Unternehmens-Betriebssystem", form, ...extras));
    },
  });

  const companyFields = [
    { name: "company_name", label: "Firmenname", required: true },
    { name: "industry", label: "Branche" },
    { name: "admin_name", label: "Ihr Name", required: true },
    { name: "admin_email", label: "Ihre E-Mail", type: "email", required: true },
    { name: "admin_password", label: "Passwort (min. 8 Zeichen)", type: "password", required: true },
  ];

  registerPage("setup", {
    title: "Einrichtung", public: true,
    async render(main) {
      const status = await api("/api/setup/status");
      if (!status.needs_setup) { location.hash = "#/login"; return; }
      const form = renderForm({
        fields: [...companyFields,
          { name: "with_demo_data", label: "Mit Demo-Daten starten (zum Ausprobieren)", type: "bool", default: false }],
        submitLabel: "KMU-OS einrichten",
        onSubmit: async (data) => {
          const result = await api("/api/setup", { method: "POST", body: data });
          setToken(result.access_token);
          state.me = null; state.setupStatus = { needs_setup: false };
          await loadMe();
          location.hash = "#/dashboard";
        },
      });
      main.append(authShell(
        "Willkommen! Richten Sie Ihr Unternehmen in einer Minute ein.", form,
        el("p", { class: "hint", style: "text-align:center" },
          "Danach: Daten per CSV importieren, Team einladen, SOPs hinterlegen — ",
          "und die KI kennt Ihr Unternehmen."),
      ));
    },
  });

  registerPage("register", {
    title: "Registrieren", public: true,
    async render(main) {
      const form = renderForm({
        fields: companyFields,
        submitLabel: "Firma registrieren",
        onSubmit: async (data) => {
          const result = await api("/api/auth/register", { method: "POST", body: data });
          setToken(result.access_token);
          state.me = null;
          await loadMe();
          location.hash = "#/dashboard";
        },
      });
      main.append(authShell("Neue Firma im KMU-OS registrieren", form));
    },
  });
}
