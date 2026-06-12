/* CRUD-Seiten der Geschäftsmodule — metadaten-getrieben über dieselben
   Bausteine, die ab Etappe 3 auch Custom-Module rendern. */

import { api } from "../api.js";
import { el, fmtEur, renderForm, renderTable, statusPill } from "../ui.js";
import { registerPage, hasPermission } from "../app.js";

const STATUS_COLORS = {
  aktiv: "ok", bezahlt: "ok", erledigt: "ok",
  offen: "warn", lead: "warn", in_arbeit: "warn", pausiert: "warn",
  "überfällig": "crit", storniert: "crit", inaktiv: "crit",
};

function crudPage({ route, title, module, listUrl, createUrl, fields, columns, mapOut }) {
  registerPage(route, {
    title, nav: true, module,
    async render(main) {
      main.append(el("h2", {}, title));
      const tableWrap = el("div", {}, el("p", { class: "hint" }, "Lade …"));
      main.append(tableWrap);

      async function reload() {
        let rows = await api(listUrl);
        if (mapOut) rows = rows.map(mapOut);
        tableWrap.innerHTML = "";
        tableWrap.append(renderTable({ columns, rows }));
      }

      if (hasPermission(module, "write")) {
        main.append(el("h2", {}, "Neu anlegen"));
        main.append(renderForm({
          fields,
          submitLabel: "Anlegen",
          onSubmit: async (data, { form, message }) => {
            await api(createUrl, { method: "POST", body: data });
            form.reset();
            message.textContent = "Gespeichert."; message.className = "success";
            await reload();
          },
        }));
      }
      await reload();
    },
  });
}

export function registerModulePages() {
  crudPage({
    route: "crm", title: "Kunden", module: "crm",
    listUrl: "/api/crm/customers", createUrl: "/api/crm/customers",
    fields: [
      { name: "name", label: "Firmenname", required: true },
      { name: "industry", label: "Branche" },
      { name: "email", label: "E-Mail", type: "email" },
      { name: "phone", label: "Telefon" },
      { name: "status", label: "Status", type: "select", options: ["lead", "aktiv", "inaktiv"] },
      { name: "notes", label: "Notizen", type: "textarea", wide: true },
    ],
    columns: [
      { key: "name", label: "Name" },
      { key: "industry", label: "Branche" },
      { key: "email", label: "E-Mail" },
      { key: "status", label: "Status", render: (r) => statusPill(r.status, STATUS_COLORS) },
      { key: "interactions", label: "Kontakte", render: (r) => String(r.interactions.length) },
    ],
  });

  crudPage({
    route: "finance", title: "Rechnungen", module: "finance",
    listUrl: "/api/finance/invoices", createUrl: "/api/finance/invoices",
    fields: [
      { name: "number", label: "Rechnungsnummer", required: true },
      { name: "amount_net", label: "Betrag netto (€)", type: "number", required: true },
      { name: "vat_rate", label: "USt. (%)", type: "number", default: 19 },
      { name: "issue_date", label: "Rechnungsdatum", type: "date", required: true },
      { name: "due_date", label: "Fällig am", type: "date" },
      { name: "status", label: "Status", type: "select", options: ["offen", "bezahlt", "storniert"] },
      { name: "description", label: "Beschreibung", wide: true },
    ],
    columns: [
      { key: "number", label: "Nummer" },
      { key: "issue_date", label: "Datum" },
      { key: "due_date", label: "Fällig" },
      { key: "amount_net", label: "Netto", render: (r) => fmtEur(r.amount_net) + " €" },
      { key: "amount_gross", label: "Brutto", render: (r) => fmtEur(r.amount_gross) + " €" },
      { key: "status", label: "Status", render: (r) => statusPill(r.status, STATUS_COLORS) },
    ],
  });

  crudPage({
    route: "expenses", title: "Ausgaben", module: "finance",
    listUrl: "/api/finance/expenses", createUrl: "/api/finance/expenses",
    fields: [
      { name: "category", label: "Kategorie", required: true },
      { name: "amount_net", label: "Betrag netto (€)", type: "number", required: true },
      { name: "expense_date", label: "Datum", type: "date", required: true },
      { name: "description", label: "Beschreibung", wide: true },
    ],
    columns: [
      { key: "expense_date", label: "Datum" },
      { key: "category", label: "Kategorie" },
      { key: "amount_net", label: "Netto", render: (r) => fmtEur(r.amount_net) + " €" },
      { key: "description", label: "Beschreibung" },
    ],
  });

  crudPage({
    route: "hr", title: "Personal", module: "hr",
    listUrl: "/api/hr/employees", createUrl: "/api/hr/employees",
    fields: [
      { name: "first_name", label: "Vorname", required: true },
      { name: "last_name", label: "Nachname", required: true },
      { name: "role", label: "Rolle/Position" },
      { name: "department", label: "Abteilung" },
      { name: "email", label: "E-Mail", type: "email" },
      { name: "weekly_hours", label: "Wochenstunden", type: "number", default: 40 },
      { name: "hired_at", label: "Eintritt", type: "date" },
    ],
    columns: [
      { key: "last_name", label: "Name", render: (r) => `${r.first_name} ${r.last_name}` },
      { key: "role", label: "Position" },
      { key: "department", label: "Abteilung" },
      { key: "weekly_hours", label: "Std./Woche" },
      { key: "absences", label: "Abwesenheiten", render: (r) => String(r.absences.length) },
    ],
  });

  crudPage({
    route: "projects", title: "Projekte", module: "projects",
    listUrl: "/api/projects", createUrl: "/api/projects",
    fields: [
      { name: "name", label: "Projektname", required: true },
      { name: "budget", label: "Budget (€)", type: "number" },
      { name: "deadline", label: "Deadline", type: "date" },
      { name: "status", label: "Status", type: "select", options: ["aktiv", "pausiert", "abgeschlossen"] },
      { name: "description", label: "Beschreibung", type: "textarea", wide: true },
    ],
    columns: [
      { key: "name", label: "Projekt" },
      { key: "deadline", label: "Deadline" },
      { key: "budget", label: "Budget", render: (r) => (r.budget ? fmtEur(r.budget) + " €" : "—") },
      { key: "status", label: "Status", render: (r) => statusPill(r.status, STATUS_COLORS) },
      { key: "tasks", label: "Aufgaben offen",
        render: (r) => String(r.tasks.filter((t) => t.status !== "erledigt").length) },
    ],
  });

  crudPage({
    route: "knowledge", title: "Wissen & SOPs", module: "knowledge",
    listUrl: "/api/knowledge/documents", createUrl: "/api/knowledge/documents",
    fields: [
      { name: "title", label: "Titel", required: true },
      { name: "doc_type", label: "Typ", type: "select",
        options: [["sop", "SOP (Arbeitsanweisung)"], ["regel", "Unternehmensregel"], ["dokument", "Dokument"]] },
      { name: "category", label: "Kategorie" },
      { name: "content", label: "Inhalt", type: "textarea", required: true, wide: true },
    ],
    columns: [
      { key: "title", label: "Titel" },
      { key: "doc_type", label: "Typ", render: (r) => statusPill(r.doc_type) },
      { key: "category", label: "Kategorie" },
      { key: "version", label: "Version", render: (r) => `v${r.version}` },
    ],
  });
}
