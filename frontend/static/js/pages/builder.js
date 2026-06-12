/* Builder: eigene Module per Form-Editor (Etappe 3) und per
   KI-Beschreibung in normalem Deutsch (Etappe 4).
   Außerdem: dynamische Seiten für aktive Custom-Module. */

import { api } from "../api.js";
import { el, renderForm, renderTable, fieldInput, readForm } from "../ui.js";
import { registerPage, hasPermission, navigate } from "../app.js";

const FIELD_TYPES = [
  ["text", "Text"], ["textarea", "Langtext"], ["number", "Zahl"],
  ["date", "Datum"], ["bool", "Ja/Nein"], ["select", "Auswahl"],
  ["reference", "Verweis"],
];

/* ---- Editor für Modul-Definitionen (auch Vorschau-Editor der KI-Entwürfe) ---- */

export function moduleEditor(initial, onSave) {
  const fieldRows = el("div");
  const message = el("div");

  function addFieldRow(field = {}) {
    const row = el("div", { class: "frow", style: "align-items:flex-end" },
      el("div", { class: "field" }, el("label", {}, "Bezeichnung"),
        el("input", { "data-k": "label", value: field.label || "" })),
      el("div", { class: "field" }, el("label", {}, "Feldname (technisch)"),
        el("input", { "data-k": "name", value: field.name || "", placeholder: "z. B. kennzeichen" })),
      el("div", { class: "field" }, el("label", {}, "Typ"),
        (() => {
          const select = el("select", { "data-k": "field_type" },
            FIELD_TYPES.map(([v, l]) => el("option", { value: v }, l)));
          select.value = field.field_type || "text";
          return select;
        })()),
      el("div", { class: "field" }, el("label", {}, "Optionen / Verweisziel"),
        el("input", { "data-k": "options", value: (field.options || []).join(", ") || field.reference_target || "",
          placeholder: "Auswahl: a, b, c — Verweis: crm/hr/projects" })),
      el("div", { class: "field", style: "max-width:90px" }, el("label", {}, "Pflicht"),
        (() => {
          const select = el("select", { "data-k": "required" },
            el("option", { value: "false" }, "Nein"), el("option", { value: "true" }, "Ja"));
          select.value = String(field.required || false);
          return select;
        })()),
      el("button", { class: "ghost small", type: "button", onclick: () => row.remove() }, "✕"));
    fieldRows.append(row);
  }

  (initial.fields || [{}]).forEach(addFieldRow);

  const nameInput = el("input", { value: initial.name || "", placeholder: "z. B. Fahrzeug" });
  const pluralInput = el("input", { value: initial.name_plural || "", placeholder: "z. B. Fuhrpark" });
  const slugInput = el("input", { value: initial.slug || "", placeholder: "z. B. fuhrpark" });
  if (initial.slugLocked) slugInput.disabled = true;
  const descInput = el("textarea", {}, initial.description || "");

  const panel = el("div", { class: "panel" },
    el("div", { class: "frow" },
      el("div", { class: "field" }, el("label", {}, "Name (Einzahl) *"), nameInput),
      el("div", { class: "field" }, el("label", {}, "Name (Mehrzahl)"), pluralInput),
      el("div", { class: "field" }, el("label", {}, "Technischer Name *"), slugInput)),
    el("div", { class: "frow" },
      el("div", { class: "field wide" }, el("label", {}, "Beschreibung"), descInput)),
    el("h2", {}, "Felder"),
    fieldRows,
    el("button", { class: "ghost", type: "button", onclick: () => addFieldRow() }, "+ Feld hinzufügen"),
    el("div", { style: "margin-top:14px" },
      el("button", {
        class: "primary", type: "button",
        onclick: async () => {
          message.textContent = ""; message.className = "";
          try {
            const fields = [...fieldRows.children].map((row) => {
              const get = (k) => row.querySelector(`[data-k="${k}"]`).value.trim();
              const fieldType = get("field_type");
              const extra = get("options");
              return {
                name: get("name") || get("label").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""),
                label: get("label"),
                field_type: fieldType,
                required: get("required") === "true",
                options: fieldType === "select" && extra ? extra.split(",").map((s) => s.trim()) : [],
                reference_target: fieldType === "reference" ? extra || null : null,
                show_in_list: true,
              };
            }).filter((f) => f.label);
            if (!fields.length) throw new Error("Mindestens ein Feld angeben");
            const definition = {
              kind: "module",
              slug: slugInput.value.trim() || nameInput.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_"),
              name: nameInput.value.trim(),
              name_plural: pluralInput.value.trim() || null,
              description: descInput.value.trim() || null,
              fields,
            };
            await onSave(definition, message);
          } catch (err) {
            message.textContent = err.message; message.className = "error";
          }
        },
      }, initial.saveLabel || "Modul erstellen"), message));
  return panel;
}

/* ---- Builder-Seite ---- */

async function modulesTab(container) {
  const modules = await api("/api/builder/modules");
  container.append(el("h2", {}, "Eigene Module"));
  container.append(renderTable({
    columns: [
      { key: "name_plural", label: "Modul", render: (m) => m.name_plural || m.name },
      { key: "slug", label: "Technisch" },
      { key: "fields", label: "Felder", render: (m) => String(m.fields.length) },
      { key: "status", label: "Status" },
      { key: "version", label: "Version", render: (m) => `v${m.version}` },
    ],
    actions: [
      { label: "Öffnen", onClick: (m) => navigate(`custom-${m.slug}`) },
      {
        label: "Archivieren",
        onClick: async (m) => {
          if (!confirm(`Modul "${m.name_plural || m.name}" wirklich archivieren?`)) return;
          await api(`/api/builder/modules/${m.slug}`, { method: "DELETE" });
          location.reload();
        },
      },
    ],
    rows: modules,
    empty: "Noch keine eigenen Module — unten erstellen oder die KI beschreiben lassen.",
  }));

  container.append(el("h2", {}, "Neues Modul (manuell)"));
  container.append(moduleEditor({}, async (definition, message) => {
    await api("/api/builder/modules", { method: "POST", body: definition });
    message.textContent = `Modul "${definition.name}" wurde erstellt.`;
    message.className = "success";
    setTimeout(() => location.reload(), 800);
  }));
}

/* ---- KI-Builder: Beschreibung in normalem Deutsch → Vorschau → Aktivieren ---- */

const KIND_LABELS = {
  module: "Eigenes Modul", automation: "Automation",
  widget: "Dashboard-Widget", workflow: "Genehmigungs-Workflow",
};

function draftCard(draft, onChange) {
  const message = el("div");
  const card = el("div", { class: "panel", style: "margin-bottom:14px" });
  card.append(
    el("h2", { style: "margin-top:0" },
      el("span", { class: "pill" }, KIND_LABELS[draft.kind] || draft.kind), " ",
      draft.definition.name || draft.definition.title || draft.definition.slug || ""));

  if (draft.kind === "module") {
    card.append(moduleEditor(
      { ...draft.definition, slugLocked: false, saveLabel: "Vorschau übernehmen & aktivieren" },
      async (definition, editorMessage) => {
        await api(`/api/builder/drafts/${draft.id}`, { method: "PATCH", body: { definition } });
        await api(`/api/builder/drafts/${draft.id}/activate`, { method: "POST" });
        editorMessage.textContent = "Aktiviert! Das Modul erscheint in der Navigation.";
        editorMessage.className = "success";
        setTimeout(() => location.reload(), 900);
      }));
  } else {
    card.append(el("pre", { class: "code" }, JSON.stringify(draft.definition, null, 2)));
    card.append(el("button", {
      class: "primary",
      onclick: async () => {
        message.textContent = ""; message.className = "";
        try {
          await api(`/api/builder/drafts/${draft.id}/activate`, { method: "POST" });
          message.textContent = "Aktiviert!"; message.className = "success";
          setTimeout(onChange, 700);
        } catch (err) {
          message.textContent = err.message; message.className = "error";
        }
      },
    }, "Aktivieren"));
  }

  card.append(el("button", {
    class: "ghost", style: "margin-left:8px",
    onclick: async () => {
      await api(`/api/builder/drafts/${draft.id}/discard`, { method: "POST" });
      onChange();
    },
  }, "Verwerfen"), message);
  return card;
}

async function aiBuilderSection(container) {
  container.append(el("h2", {}, "Per KI bauen ",
    el("span", { class: "hint" }, "— beschreiben Sie in normalem Deutsch, was Sie brauchen")));

  const input = el("textarea", {
    placeholder: "z. B.: Ich möchte unseren Fuhrpark verwalten — Kennzeichen, Marke, " +
      "TÜV-Termin und Stammfahrer. Wenn der TÜV-Termin überschritten ist, soll " +
      "automatisch eine Aufgabe entstehen. Und ich will eine Dashboard-Kachel mit " +
      "der Anzahl der Fahrzeuge in der Werkstatt.",
    style: "min-height:110px",
  });
  const button = el("button", { class: "primary" }, "Vorschlag erstellen");
  const result = el("div", { style: "margin-top:14px" });
  container.append(el("div", { class: "panel" },
    el("div", { class: "field wide" }, input),
    el("div", { style: "margin-top:10px" }, button)), result);

  async function refreshDrafts() {
    const drafts = await api("/api/builder/drafts");
    const existing = container.querySelector("#draft-list");
    if (existing) existing.remove();
    if (!drafts.length) return;
    const list = el("div", { id: "draft-list" }, el("h2", {}, "Offene Vorschläge"));
    for (const draft of drafts) list.append(draftCard(draft, refreshDrafts));
    container.append(list);
  }

  button.addEventListener("click", async () => {
    const description = input.value.trim();
    if (!description) return;
    button.disabled = true;
    result.innerHTML = "";
    result.append(el("p", { class: "hint" }, "Die KI analysiert Ihre Anforderung …"));
    try {
      const data = await api("/api/builder/draft", { method: "POST", body: { description } });
      result.innerHTML = "";
      result.append(el("div", { class: "finding info" },
        el("span", { class: "area" }, "KI-Vorschlag"), el("br"), data.erklaerung));
      for (const frage of data.rueckfragen || [])
        result.append(el("div", { class: "finding warnung" },
          el("span", { class: "area" }, "Rückfrage"), el("br"), frage));
      await refreshDrafts();
    } catch (err) {
      result.innerHTML = "";
      result.append(el("p", { class: "error" }, err.message));
    }
    button.disabled = false;
  });

  await refreshDrafts();
}

export function registerBuilderPages() {
  registerPage("builder", {
    title: "Builder", nav: true, module: "builder",
    async render(main) {
      main.append(el("h2", {}, "Builder ",
        el("span", { class: "hint" }, "— passen Sie das KMU-OS an Ihr Unternehmen an")));
      const aiContainer = el("div");
      const container = el("div");
      main.append(aiContainer, container);
      await aiBuilderSection(aiContainer);
      await modulesTab(container);
    },
  });
}

/* ---- Dynamische Seiten für aktive Custom-Module ---- */

function recordFormFields(module) {
  return module.fields.map((field) => ({
    name: field.name,
    label: field.label + (field.field_type === "reference" ? ` (ID aus ${field.reference_target})` : ""),
    type: { textarea: "textarea", number: "number", date: "date", bool: "bool", select: "select" }[field.field_type]
      || (field.field_type === "reference" ? "number" : "text"),
    options: field.options,
    required: field.required,
    wide: field.field_type === "textarea",
  }));
}

export async function ensureCustomModules() {
  let modules = [];
  try { modules = await api("/api/custom/modules"); } catch { return; }
  for (const module of modules) {
    registerPage(`custom-${module.slug}`, {
      title: module.name_plural || module.name,
      nav: true, module: `custom:${module.slug}`,
      async render(main) {
        main.append(el("h2", {}, module.name_plural || module.name,
          module.description ? el("span", { class: "hint" }, " — " + module.description) : ""));
        const tableWrap = el("div", {}, el("p", { class: "hint" }, "Lade …"));
        main.append(tableWrap);

        async function reload() {
          const data = await api(`/api/custom/${module.slug}/records`);
          const listFields = data.module.fields.filter((f) => f.show_in_list);
          tableWrap.innerHTML = "";
          tableWrap.append(renderTable({
            columns: listFields.map((f) => ({
              key: f.name, label: f.label,
              render: (r) => {
                const value = r.values[f.name];
                if (value === null || value === undefined || value === "") return "—";
                if (f.field_type === "bool") return value ? "Ja" : "Nein";
                return String(value);
              },
            })),
            actions: hasPermission(`custom:${module.slug}`, "write") ? [{
              label: "Löschen",
              onClick: async (r) => {
                if (!confirm("Eintrag wirklich löschen?")) return;
                await api(`/api/custom/${module.slug}/records/${r.id}`, { method: "DELETE" });
                await reload();
              },
            }] : [],
            rows: data.records,
          }));
        }

        if (hasPermission(`custom:${module.slug}`, "write")) {
          main.append(el("h2", {}, `${module.name} anlegen`));
          main.append(renderForm({
            fields: recordFormFields(module),
            submitLabel: "Anlegen",
            onSubmit: async (data, { form, message }) => {
              const values = Object.fromEntries(
                Object.entries(data).filter(([, v]) => v !== null));
              await api(`/api/custom/${module.slug}/records`, { method: "POST", body: values });
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
}
