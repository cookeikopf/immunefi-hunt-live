/* Administration: Benutzer, Rollen (Rechte-Matrix), CSV-Import. */

import { api } from "../api.js";
import { el, renderForm, renderTable } from "../ui.js";
import { registerPage } from "../app.js";

const MODULE_LABELS = {
  crm: "Kunden", finance: "Finanzen", hr: "Personal", projects: "Projekte",
  knowledge: "Wissen", ai: "KI-Assistent", builder: "Builder",
  workflows: "Workflows", admin: "Administration",
};

async function usersTab(container) {
  const [users, roles] = await Promise.all([api("/api/admin/users"), api("/api/admin/roles")]);
  const roleOptions = roles.map((r) => [r.id, r.name]);

  container.append(el("h2", {}, "Benutzer"));
  container.append(renderTable({
    columns: [
      { key: "display_name", label: "Name" },
      { key: "email", label: "E-Mail" },
      { key: "role", label: "Rolle" },
      { key: "active", label: "Aktiv", render: (u) => (u.active ? "✓" : "—") },
    ],
    actions: [{
      label: "Sperren/Aktivieren",
      onClick: async (u) => {
        await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { active: !u.active } });
        container.innerHTML = ""; await usersTab(container);
      },
    }],
    rows: users,
  }));

  container.append(el("h2", {}, "Benutzer anlegen"));
  container.append(renderForm({
    fields: [
      { name: "display_name", label: "Name", required: true },
      { name: "email", label: "E-Mail", type: "email", required: true },
      { name: "password", label: "Passwort (min. 8 Zeichen)", type: "password", required: true },
      { name: "role_id", label: "Rolle", type: "select", options: roleOptions, required: true },
    ],
    submitLabel: "Anlegen",
    onSubmit: async (data, { form, message }) => {
      await api("/api/admin/users", { method: "POST", body: { ...data, role_id: Number(data.role_id) } });
      form.reset();
      message.textContent = "Benutzer angelegt."; message.className = "success";
      container.innerHTML = ""; await usersTab(container);
    },
  }));
}

async function rolesTab(container) {
  const [roles, catalog] = await Promise.all([api("/api/admin/roles"), api("/api/admin/modules")]);
  container.append(el("h2", {}, "Rollen & Rechte"),
    el("p", { class: "hint" },
      "Pro Modul: kein Zugriff, nur lesen oder lesen + schreiben. ",
      "Die Admin-Rolle ist geschützt."));

  for (const role of roles) {
    const editable = !(role.is_system && role.name === "Admin");
    const permissionOf = (module) =>
      role.permissions.find((p) => p.module === module || p.module === "*")?.action ?? "";

    const rows = catalog.modules.map((module) => {
      const select = el("select", { disabled: editable ? undefined : "disabled" },
        el("option", { value: "" }, "kein Zugriff"),
        el("option", { value: "read" }, "lesen"),
        el("option", { value: "write" }, "lesen + schreiben"));
      select.value = permissionOf(module);
      select.dataset.module = module;
      return el("tr", {}, el("td", {}, MODULE_LABELS[module] || module), el("td", {}, select));
    });

    const panel = el("div", { class: "panel", style: "margin-bottom:16px" },
      el("h2", { style: "margin-top:0" }, role.name, " ",
        role.is_system ? el("span", { class: "pill" }, "System") : ""),
      el("table", { class: "matrix" },
        el("tr", {}, el("th", {}, "Modul"), el("th", {}, "Zugriff")), rows));

    if (editable) {
      const message = el("span");
      panel.append(el("button", {
        class: "ghost", style: "margin-top:10px",
        onclick: async (event) => {
          const permissions = [...panel.querySelectorAll("select")]
            .filter((s) => s.value)
            .map((s) => ({ module: s.dataset.module, action: s.value }));
          try {
            await api(`/api/admin/roles/${role.id}`, { method: "PATCH", body: { permissions } });
            message.textContent = " Gespeichert."; message.className = "success";
          } catch (err) {
            message.textContent = " " + err.message; message.className = "error";
          }
        },
      }, "Rechte speichern"), message);
    }
    container.append(panel);
  }

  container.append(el("h2", {}, "Neue Rolle"));
  container.append(renderForm({
    fields: [{ name: "name", label: "Rollenname", required: true }],
    submitLabel: "Rolle anlegen",
    onSubmit: async (data) => {
      await api("/api/admin/roles", { method: "POST", body: { name: data.name, permissions: [] } });
      container.innerHTML = ""; await rolesTab(container);
    },
  }));
}

async function importTab(container) {
  container.append(el("h2", {}, "CSV-Import"),
    el("p", { class: "hint" }, "Bestandsdaten in Minuten übernehmen. Trennzeichen ; oder , — wird automatisch erkannt."));

  const targets = [
    { url: "/api/imports/customers", label: "Kunden",
      columns: "name*; industry; email; phone; address; status; notes" },
    { url: "/api/imports/invoices", label: "Rechnungen",
      columns: "number*; amount_net*; issue_date* (JJJJ-MM-TT); due_date; vat_rate; status; customer_name" },
  ];

  for (const target of targets) {
    const input = el("input", { type: "file", accept: ".csv" });
    const message = el("div");
    const panel = el("div", { class: "panel", style: "margin-bottom:16px" },
      el("h2", { style: "margin-top:0" }, target.label),
      el("p", { class: "hint" }, "Spalten: ", el("code", {}, target.columns)),
      el("div", { class: "frow" },
        el("div", { class: "field" }, input),
        el("button", {
          class: "primary",
          onclick: async () => {
            if (!input.files.length) { message.textContent = "Bitte Datei wählen."; message.className = "error"; return; }
            const body = new FormData();
            body.append("file", input.files[0]);
            try {
              const report = await api(target.url, { method: "POST", body });
              message.className = report.errors.length ? "error" : "success";
              message.textContent = `${report.imported} von ${report.total} Zeilen importiert.`;
              if (report.errors.length) {
                const list = el("ul", {}, report.errors.slice(0, 10).map(
                  (e) => el("li", {}, `Zeile ${e.row}: ${e.error}`)));
                message.append(list);
              }
            } catch (err) {
              message.textContent = err.message; message.className = "error";
            }
          },
        }, "Importieren")),
      message);
    container.append(panel);
  }

  const jobs = await api("/api/imports/jobs");
  if (jobs.length) {
    container.append(el("h2", {}, "Letzte Importe"));
    container.append(renderTable({
      columns: [
        { key: "created_at", label: "Zeitpunkt", render: (j) => new Date(j.created_at).toLocaleString("de-DE") },
        { key: "kind", label: "Art" },
        { key: "filename", label: "Datei" },
        { key: "imported", label: "Importiert", render: (j) => `${j.imported}/${j.total}` },
        { key: "errors", label: "Fehler", render: (j) => String(j.errors.length) },
      ],
      rows: jobs,
    }));
  }
}

export function registerAdminPages() {
  registerPage("admin", {
    title: "Administration", nav: true, module: "admin",
    async render(main) {
      const tabs = [
        ["Benutzer", usersTab],
        ["Rollen & Rechte", rolesTab],
        ["Datenimport", importTab],
      ];
      const bar = el("div", { class: "tabs" });
      const content = el("div");
      main.append(bar, content);
      let buttons = [];
      const open = async (index) => {
        buttons.forEach((b, i) => b.classList.toggle("active", i === index));
        content.innerHTML = "";
        await tabs[index][1](content);
      };
      buttons = tabs.map(([label], index) =>
        el("button", { onclick: () => open(index) }, label));
      bar.append(...buttons);
      await open(0);
    },
  });
}
