/* Kernseiten: Dashboard (KPIs), Firmen-Assistent (Chat), KI-Insights. */

import { api } from "../api.js";
import { el, fmtEur, fmtNum } from "../ui.js";
import { registerPage } from "../app.js";

export function registerCorePages() {
  registerPage("dashboard", {
    title: "Dashboard", nav: true, module: "ai",
    async render(main) {
      main.append(el("h2", {}, "Kennzahlen aller Bereiche"));
      const grid = el("div", { class: "grid" }, el("p", { class: "hint" }, "Lade …"));
      main.append(grid);
      const k = await api("/api/ai/kpis");
      const cards = [
        ["Umsatz (netto)", fmtEur(k.finanzen.umsatz_gesamt_netto), "eur"],
        ["Ergebnis (netto)", fmtEur(k.finanzen.ergebnis_netto), "eur"],
        ["Offene Rechnungen", k.finanzen.offene_rechnungen],
        ["Überfällig", k.finanzen.ueberfaellige_rechnungen],
        ["Kunden", k.vertrieb.kunden_gesamt],
        ["Leads", k.vertrieb.leads],
        ["Mitarbeitende", k.personal.mitarbeiter_aktiv],
        ["Aktive Projekte", k.projekte.projekte_aktiv],
        ["Offene Aufgaben", k.projekte.aufgaben_offen],
        ["Wissensdokumente", k.wissen.dokumente],
      ];
      grid.innerHTML = "";
      for (const [label, value, cls] of cards)
        grid.append(el("div", { class: "card" },
          el("div", { class: "label" }, label),
          el("div", { class: `value ${cls || ""}` }, String(value))));

      // Einhängepunkt für Builder-Widgets (Etappe 7)
      main.append(el("div", { id: "custom-widgets" }));
    },
  });

  registerPage("assistant", {
    title: "Firmen-Assistent", nav: true, module: "ai",
    async render(main) {
      main.append(el("h2", {}, "Firmen-Assistent ",
        el("span", { class: "hint" }, "— kennt SOPs, Regeln, Kunden, Projekte & Zahlen")));
      const log = el("div", { id: "chat-log" },
        el("p", { class: "hint" },
          'Fragen Sie z. B.: „Wie läuft unser Onboarding?" oder „Welche Rechnungen sind überfällig?"'));
      const input = el("input", { placeholder: "Frage an das Unternehmen stellen …", autocomplete: "off" });
      const button = el("button", { class: "primary" }, "Fragen");
      const form = el("form", { class: "frow", style: "margin-top:14px" },
        el("div", { class: "field", style: "flex:1" }, input), button);
      main.append(log, form);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = input.value.trim();
        if (!question) return;
        if (log.querySelector(".hint")) log.innerHTML = "";
        log.append(el("div", { class: "msg user" }, el("div", { class: "who" }, "Sie"), question));
        input.value = ""; button.disabled = true;
        log.scrollTop = log.scrollHeight;
        try {
          const data = await api("/api/ai/chat", { method: "POST", body: { question } });
          const sourceTitles = [...new Set(data.sources.map((s) => s.title))];
          const answer = el("div", { class: "msg" },
            el("div", { class: "who" }, "KMU-OS Assistent"),
            el("pre", {}, data.answer));
          if (sourceTitles.length)
            answer.append(el("div", { class: "sources" }, "Quellen: " + sourceTitles.join(" · ")));
          log.append(answer);
        } catch (err) {
          log.append(el("div", { class: "msg" }, el("div", { class: "who" }, "Fehler"), err.message));
        }
        button.disabled = false;
        log.scrollTop = log.scrollHeight;
      });
    },
  });

  registerPage("insights", {
    title: "KI-Insights", nav: true, module: "ai",
    async render(main) {
      main.append(el("h2", {}, "Befunde"));
      const findings = el("div", {}, el("p", { class: "hint" }, "Analysiere …"));
      main.append(findings, el("h2", {}, "KI-Verbesserungsvorschläge"));
      const suggestions = el("div", { id: "ai-suggestions", class: "hint" },
        "Claude analysiert die gebündelten Unternehmensdaten …");
      main.append(suggestions);

      const data = await api("/api/ai/insights");
      findings.innerHTML = "";
      if (!data.findings.length)
        findings.append(el("p", { class: "hint" }, "Keine Auffälligkeiten erkannt."));
      for (const f of data.findings)
        findings.append(el("div", { class: `finding ${f.severity}` },
          el("span", { class: "area" }, `${f.area} · ${f.severity}`),
          el("br"), f.message));
      suggestions.className = "";
      suggestions.id = "ai-suggestions";
      suggestions.textContent = data.ai_suggestions;
    },
  });
}
