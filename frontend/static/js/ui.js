/* UI-Bausteine: Element-Helfer, generische Formulare und Tabellen.
   renderForm/renderTable sind metadaten-getrieben — dieselben Bausteine
   rendern ab Etappe 3 auch die Custom-Module des Builders. */

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

export const fmtEur = (n) =>
  Number(n).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtNum = (n) => Number(n).toLocaleString("de-DE", { maximumFractionDigits: 2 });

/* Feld-Definition: {name, label, type: text|number|date|bool|select|textarea,
   options: [..] (für select), required, default} */
export function fieldInput(field, value) {
  const val = value ?? field.default ?? "";
  if (field.type === "textarea")
    return el("textarea", { name: field.name }, String(val));
  if (field.type === "select") {
    const select = el("select", { name: field.name });
    for (const opt of field.options || []) {
      const [v, label] = Array.isArray(opt) ? opt : [opt, opt];
      const option = el("option", { value: v }, label);
      if (String(v) === String(val)) option.selected = true;
      select.append(option);
    }
    return select;
  }
  if (field.type === "bool") {
    const select = el("select", { name: field.name },
      el("option", { value: "true" }, "Ja"), el("option", { value: "false" }, "Nein"));
    select.value = String(val === "" ? true : val);
    return select;
  }
  const typeMap = { number: "number", date: "date", password: "password", email: "email" };
  const input = el("input", {
    name: field.name, type: typeMap[field.type] || "text", value: String(val),
  });
  if (field.type === "number") input.step = "any";
  return input;
}

export function readForm(form, fields) {
  const data = {};
  for (const field of fields) {
    const input = form.elements[field.name];
    if (!input) continue;
    let value = input.value.trim();
    if (value === "" && !field.required) { data[field.name] = null; continue; }
    if (field.type === "number") value = value === "" ? null : Number(value);
    if (field.type === "bool") value = input.value === "true";
    data[field.name] = value;
  }
  return data;
}

export function renderForm({ fields, submitLabel = "Speichern", onSubmit, values = {} }) {
  const message = el("div");
  const form = el("form", { class: "panel" });
  const row = el("div", { class: "frow" });
  for (const field of fields) {
    row.append(el("div", { class: `field ${field.wide ? "wide" : ""}` },
      el("label", {}, field.label + (field.required ? " *" : "")),
      fieldInput(field, values[field.name])));
  }
  const button = el("button", { class: "primary" }, submitLabel);
  form.append(row, button, message);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = ""; message.className = "";
    button.disabled = true;
    try {
      const data = readForm(form, fields);
      for (const field of fields)
        if (field.required && (data[field.name] === null || data[field.name] === ""))
          throw new Error(`"${field.label}" ist ein Pflichtfeld`);
      await onSubmit(data, { form, message });
    } catch (err) {
      message.textContent = err.message; message.className = "error";
    } finally {
      button.disabled = false;
    }
  });
  return form;
}

/* columns: [{key, label, render?(row)}], actions: [{label, onClick(row)}] */
export function renderTable({ columns, rows, actions = [], empty = "Keine Einträge." }) {
  if (!rows.length) return el("p", { class: "hint" }, empty);
  const head = el("tr", {}, columns.map((c) => el("th", {}, c.label)),
    actions.length ? el("th", {}, "") : null);
  const body = rows.map((row) =>
    el("tr", {},
      columns.map((c) => el("td", {}, c.render ? c.render(row) : String(row[c.key] ?? "—"))),
      actions.length
        ? el("td", {}, el("div", { class: "row-actions" },
            actions.map((a) => el("button", { class: "ghost small", onclick: () => a.onClick(row) }, a.label))))
        : null));
  return el("table", {}, head, body);
}

export function statusPill(status, map = {}) {
  const cls = map[status] || "";
  return el("span", { class: `pill ${cls}` }, status);
}
