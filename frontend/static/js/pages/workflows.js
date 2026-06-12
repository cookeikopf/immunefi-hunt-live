/* Workflows: Genehmigungs-Inbox, alle Vorgänge, Definitionen. */

import { api } from "../api.js";
import { el, renderTable } from "../ui.js";
import { registerPage } from "../app.js";

const STATUS_CLS = { offen: "warn", genehmigt: "ok", abgelehnt: "crit" };

function instanceCard(instance, withActions, onChange) {
  const message = el("div");
  const card = el("div", { class: "panel", style: "margin-bottom:14px" },
    el("h2", { style: "margin-top:0" },
      instance.workflow, " ",
      el("span", { class: `pill ${STATUS_CLS[instance.status]}` }, instance.status),
      instance.status === "offen"
        ? el("span", { class: "hint" },
            ` — Stufe ${instance.current_step + 1}/${instance.steps_total}: `
            + `${instance.current_step_name} (${instance.current_approver_role})`)
        : ""),
    el("pre", { class: "code" }, instance.subject_summary));

  for (const approval of instance.approvals)
    card.append(el("p", { class: "hint" },
      `Stufe ${approval.step_index + 1}: ${approval.decision}`
      + (approval.comment ? ` — „${approval.comment}"` : "")));

  if (withActions && instance.status === "offen") {
    const comment = el("input", { placeholder: "Kommentar (optional)" });
    const act = async (decision) => {
      message.textContent = ""; message.className = "";
      try {
        await api(`/api/workflows/instances/${instance.id}/decide`, {
          method: "POST", body: { decision, comment: comment.value.trim() || null },
        });
        onChange();
      } catch (err) {
        message.textContent = err.message; message.className = "error";
      }
    };
    card.append(el("div", { class: "frow", style: "margin-top:10px" },
      el("div", { class: "field", style: "flex:2" }, comment),
      el("button", { class: "primary", onclick: () => act("genehmigt") }, "Genehmigen"),
      el("button", { class: "ghost", onclick: () => act("abgelehnt") }, "Ablehnen")),
      message);
  }
  return card;
}

export default function registerWorkflowPages() {
  registerPage("workflows", {
    title: "Genehmigungen", nav: true, module: "workflows",
    async render(main) {
      main.append(el("h2", {}, "Meine Genehmigungen"));
      const inboxWrap = el("div");
      main.append(inboxWrap);

      async function reload() {
        const [inbox, all, definitions] = await Promise.all([
          api("/api/workflows/inbox"),
          api("/api/workflows/instances"),
          api("/api/workflows/definitions"),
        ]);
        inboxWrap.innerHTML = "";
        if (!inbox.length)
          inboxWrap.append(el("p", { class: "hint" }, "Keine offenen Genehmigungen für Sie."));
        for (const instance of inbox)
          inboxWrap.append(instanceCard(instance, true, reload));

        inboxWrap.append(el("h2", {}, "Alle Vorgänge"));
        inboxWrap.append(renderTable({
          columns: [
            { key: "workflow", label: "Workflow" },
            { key: "subject_ref", label: "Betrifft" },
            { key: "status", label: "Status",
              render: (i) => el("span", { class: `pill ${STATUS_CLS[i.status]}` }, i.status) },
            { key: "current_step", label: "Stufe",
              render: (i) => i.status === "offen" ? `${i.current_step + 1}/${i.steps_total}` : "—" },
            { key: "created_at", label: "Gestartet",
              render: (i) => new Date(i.created_at).toLocaleString("de-DE") },
          ],
          rows: all,
          empty: "Noch keine Vorgänge.",
        }));

        if (definitions.length) {
          inboxWrap.append(el("h2", {}, "Eingerichtete Workflows"));
          inboxWrap.append(renderTable({
            columns: [
              { key: "name", label: "Name" },
              { key: "trigger_event", label: "Startet bei" },
              { key: "steps", label: "Stufen",
                render: (d) => d.steps.map((s) => s.approver_role).join(" → ") },
              { key: "active", label: "Status",
                render: (d) => el("span", { class: `pill ${d.active ? "ok" : "crit"}` },
                  d.active ? "aktiv" : "pausiert") },
            ],
            rows: definitions,
          }));
        }
      }
      await reload();
    },
  });
}
