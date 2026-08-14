const API = "https://pruefpilot-v5-api.vercel.app";

const fallbackCases = [
  {
    id: "glasfaser-sonnenhain",
    internal_id: "GF-2026-014",
    title: "Glasfaser-Ausbau Sonnenhain",
    question: "Kann die Schlusszahlung vorbereitet werden?",
    domain: "Fördermittelprüfung",
    user: "Fördermittelprüfer:in",
    status: "Prüfung erforderlich",
    metrics: [
      { value: "7/9", label: "Pflichtunterlagen" },
      { value: "4.280 €", label: "ungeklärte Differenz" },
      { value: "1", label: "Quarantänefall" },
    ],
    tech_mode: "live-api",
  },
  {
    id: "wohngeld-vollstaendigkeit",
    internal_id: "WG-DEMO-041",
    title: "Wohngeldantrag einer vierköpfigen Familie",
    question: "Welche Unterlagen fehlen noch?",
    domain: "Bürgerdienst",
    user: "Sachbearbeiter:in / Bürgerberatung",
    status: "Nachforderung vorbereiten",
    metrics: [
      { value: "4/6", label: "Kernunterlagen" },
      { value: "130 €", label: "Einkommensabweichung" },
      { value: "2", label: "Nachforderungen" },
    ],
    tech_mode: "domain-pack-preview",
  },
  {
    id: "vergaberegel-schul-it",
    internal_id: "VR-DEMO-2027",
    title: "Neue Vergaberegel für kommunale Schul-IT",
    question: "Welche laufenden Projekte sind betroffen?",
    domain: "Rechtsänderung & Vergabe",
    user: "Verwaltungsjurist:in / Projektleitung",
    status: "Drei Vorgänge prüfen",
    metrics: [
      { value: "2", label: "Regelversionen" },
      { value: "3", label: "mögliche Treffer" },
      { value: "1", label: "hoher Handlungsbedarf" },
    ],
    tech_mode: "gitlaw-bridge-preview",
  },
];

const fallbackDetails = {
  "glasfaser-sonnenhain": {
    ...fallbackCases[0],
    goal: "Fehlende Unterlagen, Zahlendifferenzen und unbelegte Aussagen vor der menschlichen Freigabe erkennen.",
    next_action: "Abnahmeprotokoll und GPS-Fotos nachfordern; R-007 und die Differenz von 4.280 EUR klären.",
    documents: [
      { name: "Bewilligungsbescheid.pdf", status: "vorhanden", excerpt: "Bewilligungszeitraum und Nebenbestimmungen." },
      { name: "Rechnungspaket_R001-R007.pdf", status: "vorhanden", excerpt: "Rechnungssumme 734.280 EUR; R-007 ohne Leistungszeitraum." },
      { name: "Abnahmeprotokoll.pdf", status: "fehlt", excerpt: "Pflichtunterlage fehlt." },
      { name: "GPS-Fotodokumentation.zip", status: "fehlt", excerpt: "Pflichtunterlage fehlt." },
      { name: "Lieferantenhinweis.pdf", status: "quarantaene", excerpt: "Prompt-Injection-Demo." },
    ],
    confirmed: ["Kernunterlagen liegen vor.", "R-001 bis R-006 sind formal zuordenbar."],
    open: ["Abnahmeprotokoll fehlt.", "GPS-Fotodokumentation fehlt.", "4.280 EUR Differenz ungeklärt."],
    suggested_questions: ["Welche Unterlagen fehlen?", "Welche Beträge stimmen nicht überein?", "Kann die Schlusszahlung freigegeben werden?"],
    tech: {
      mode: "live-api",
      tools: ["check_completeness", "reconcile_amounts", "scan_prompt_injection"],
      domain_pack: ["required_documents.yaml", "funding_rules.json", "amount_checks.py"],
    },
  },
  "wohngeld-vollstaendigkeit": {
    ...fallbackCases[1],
    goal: "Die Vollständigkeit erklären und gezielte Nachforderungen vorbereiten, ohne über den Anspruch zu entscheiden.",
    next_action: "Nebenkostennachweis und Unterhaltsbeleg anfordern; Einkommensangabe klären.",
    documents: [
      { name: "Wohngeldantrag.pdf", status: "vorhanden", excerpt: "Vier Personen; Bruttokaltmiete 1.120 EUR." },
      { name: "Mietvertrag.pdf", status: "vorhanden", excerpt: "Bruttokaltmiete stimmt überein." },
      { name: "Einkommensnachweise.pdf", status: "pruefen", excerpt: "130 EUR Abweichung zur Antragsangabe." },
      { name: "Nebenkostenabrechnung.pdf", status: "fehlt", excerpt: "Aktueller Nachweis fehlt." },
      { name: "Unterhaltsnachweis.pdf", status: "fehlt", excerpt: "Unterhaltszahlung nicht belegt." },
    ],
    confirmed: ["Antrag, Mietvertrag und Meldebescheinigung liegen vor.", "Mietangabe stimmt überein."],
    open: ["Nebenkostennachweis fehlt.", "Unterhaltsbeleg fehlt.", "130 EUR Einkommensabweichung."],
    suggested_questions: ["Welche Unterlagen fehlen?", "Welche Angaben widersprechen sich?", "Ist der Antrag vollständig?"],
    tech: {
      mode: "domain-pack-preview",
      tools: ["check_required_documents", "compare_declared_income", "prepare_request_for_information"],
      domain_pack: ["wohngeld_case_schema.json", "required_documents.yaml", "consistency_checks.py"],
    },
  },
  "vergaberegel-schul-it": {
    ...fallbackCases[2],
    goal: "Eine Regeländerung versioniert verstehen und auf laufende Vorgänge anwenden.",
    next_action: "Schulcampus Nord priorisiert prüfen; bei zwei Vorgängen den Vergabestart klären.",
    documents: [
      { name: "Vergaberegel_2026.pdf", status: "vorhanden", excerpt: "Bisherige Regelversion." },
      { name: "Vergaberegel_2027.pdf", status: "vorhanden", excerpt: "Neue Marktpreisprüfung ab 01.01.2027." },
      { name: "Projektliste_Schul-IT.xlsx", status: "vorhanden", excerpt: "Acht laufende Vorgänge." },
      { name: "Vergabevermerk_Schulcampus_Nord.pdf", status: "pruefen", excerpt: "Keine dokumentierte Marktpreisprüfung." },
    ],
    confirmed: ["Neue Regel gilt ab 01.01.2027.", "Tablets West erfüllt die neue Anforderung."],
    open: ["Schulcampus Nord ohne Marktpreisprüfung.", "Bei zwei Vorgängen ist der Vergabestart unklar."],
    suggested_questions: ["Was hat sich 2027 geändert?", "Welche Projekte sind betroffen?", "Wie hängt das mit GitLaw zusammen?"],
    tech: {
      mode: "gitlaw-bridge-preview",
      tools: ["compare_rule_versions", "match_projects_to_rule", "draft_impact_note"],
      domain_pack: ["versioned_rules.json", "project_schema.json", "impact_checks.py"],
    },
  },
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#039;",
})[char]);

let cases = fallbackCases;
let currentId = "glasfaser-sonnenhain";
let current = fallbackDetails[currentId];
let mode = "fach";
let tourIndex = 0;

async function getJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function renderCases() {
  $("#caseGrid").innerHTML = cases.map((item, index) => `
    <button class="caseCard ${item.id === currentId ? "active" : ""}" data-id="${item.id}">
      <div>
        <small>${String(index + 1).padStart(2, "0")} · ${escapeHtml(item.domain)}</small>
        <h3>${escapeHtml(item.title)}</h3>
        <div class="bigq">${escapeHtml(item.question)}</div>
        <p>${escapeHtml(item.user)}</p>
      </div>
      <div class="caseMeta"><span>${escapeHtml(item.status)}</span><span>${escapeHtml(item.tech_mode)}</span></div>
    </button>
  `).join("");
  $$(".caseCard").forEach((button) => {
    button.addEventListener("click", () => selectCase(button.dataset.id, true));
  });
}

function renderMode() {
  const technical = mode === "technik";
  $("#modeStatus").textContent = technical ? `TECH MODE · ${current.tech.mode}` : `FACHANSICHT · ${current.user}`;
  $("#trace").classList.toggle("visible", technical);
  if (technical) {
    $("#trace").innerHTML = `
      <div class="traceMeta">
        <div><small>DOMAIN PACK</small>${current.tech.domain_pack.map(escapeHtml).join("<br>")}</div>
        <div><small>TOOLS</small>${current.tech.tools.map(escapeHtml).join("<br>")}</div>
        <div><small>BOUNDARY</small>typed output<br>grounded sources<br>human approval</div>
      </div>
      <div class="traceRow"><b>select_case</b><span>${escapeHtml(current.id)}</span></div>
      <div class="traceRow"><b>load_domain_pack</b><span>${escapeHtml(current.domain)}</span></div>
      <div class="traceRow"><b>await_question</b><span>bereit</span></div>
    `;
  }
}

function renderWorkspace() {
  if (!current) return;
  $("#caseIdentity").textContent = `${current.domain} · ${current.internal_id} · alle Daten synthetisch`;
  $("#caseTitle").textContent = current.title;
  $("#caseGoal").textContent = current.goal;
  $("#nextAction").textContent = current.next_action;
  $("#documentCount").textContent = `${current.documents.length} Dateien`;
  $("#documents").innerHTML = current.documents.map((doc, index) => `
    <button class="doc" data-doc="${index}" data-status="${escapeHtml(doc.status)}">
      <i></i><span>${escapeHtml(doc.name)}</span><small>${escapeHtml(doc.status).toUpperCase()}</small>
    </button>
  `).join("");
  $$(".doc").forEach((button) => button.addEventListener("click", () => openDocument(Number(button.dataset.doc))));
  $("#metrics").innerHTML = current.metrics.map((metric) => `<div class="metric"><strong>${escapeHtml(metric.value)}</strong><span>${escapeHtml(metric.label)}</span></div>`).join("");
  $("#findings").innerHTML = `
    <article class="card teal"><h4>Bestätigt</h4><ul>${current.confirmed.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>
    <article class="card ${current.open.length > 2 ? "sand" : "lime"}"><h4>Offen / prüfen</h4><ul>${current.open.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>
  `;
  $("#question").value = current.question;
  $("#suggestions").innerHTML = current.suggested_questions.map((question) => `<button>${escapeHtml(question)}</button>`).join("");
  $$("#suggestions button").forEach((button) => button.addEventListener("click", () => {
    $("#question").value = button.textContent;
    ask();
  }));
  $("#answer").innerHTML = `<small>BEREIT</small><h4>${escapeHtml(current.question)}</h4><p>Stellen Sie die vorgeschlagene Frage oder formulieren Sie eine eigene.</p>`;
  renderMode();
}

async function selectCase(id, scroll = false) {
  currentId = id;
  renderCases();
  $(".workspace").classList.add("case-changing");
  try {
    current = await getJSON(`${API}/api/v5/cases/${id}`);
  } catch {
    current = fallbackDetails[id];
  }
  renderWorkspace();
  requestAnimationFrame(() => $(".workspace").classList.remove("case-changing"));
  if (scroll) $("#workspace").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function ask() {
  const button = $("#askBtn");
  const question = $("#question").value.trim();
  if (question.length < 3) return;
  button.disabled = true;
  button.textContent = "Prüfe…";

  let payload;
  try {
    payload = await getJSON(`${API}/api/v5/cases/${currentId}/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    payload = {
      answer: `${current.confirmed.join(" ")} ${current.open.join(" ")} Nächste Aktion: ${current.next_action}`,
      grounded: false,
      fallback: true,
      uncertainty: "demo",
      citations: [],
      trace: [{ tool: "static_demo_fallback", detail: "Live-Backend nicht erreichbar; synthetische Falldaten lokal angezeigt", duration_ms: 0 }],
      tech_mode: current.tech.mode,
    };
  }

  let label;
  let heading;
  if (payload.fallback) {
    label = "STATIC DEMO FALLBACK · NICHT LIVE VERIFIZIERT";
    heading = "Synthetischer Demo-Fall";
  } else if (payload.grounded) {
    label = `QUELLENBASIERTE ANTWORT · ${escapeHtml(payload.uncertainty || "")}`;
    heading = "Ergebnis für den ausgewählten Fall";
  } else {
    label = `GROUNDING GUARD · ${escapeHtml(payload.uncertainty || "")}`;
    heading = "Keine belastbare Grundlage";
  }

  $("#answer").innerHTML = `
    <small>${label}</small>
    <h4>${heading}</h4>
    <p>${escapeHtml(payload.answer)}</p>
    ${(payload.citations || []).map((citation) => `<a class="citation" href="${escapeHtml(citation.source_url)}" target="_blank"><b>${escapeHtml(citation.title)} · S. ${escapeHtml(citation.page)}</b><span>${escapeHtml(citation.version)} · ${escapeHtml(citation.section)}</span></a>`).join("")}
  `;

  if (mode === "technik") {
    $("#trace").innerHTML = `
      <div class="traceMeta"><div><small>CASE</small>${escapeHtml(current.internal_id)}</div><div><small>MODE</small>${escapeHtml(payload.tech_mode || current.tech.mode)}</div><div><small>BOUNDARY</small>${payload.fallback ? "static demo only" : "human approval required"}</div></div>
      ${(payload.trace || []).map((step) => `<div class="traceRow"><b>${escapeHtml(step.tool)}</b><span>${escapeHtml(step.detail)} · ${escapeHtml(step.duration_ms || 0)} ms</span></div>`).join("")}
    `;
  }

  button.disabled = false;
  button.textContent = "Antwort prüfen";
}

function openDocument(index) {
  const doc = current.documents[index];
  $("#modalTitle").textContent = doc.name;
  $("#modalExcerpt").textContent = `STATUS: ${doc.status.toUpperCase()}\nFALL: ${current.title}\n\n${doc.excerpt}\n\nHinweis: vollständig synthetischer Demo-Auszug.`;
  $("#modal").classList.add("open");
}

const tourSteps = [
  { id: "glasfaser-sonnenhain", title: "Fördermittelprüfung verstehen", text: "Kann die Schlusszahlung vorbereitet werden?", mode: "fach" },
  { id: "glasfaser-sonnenhain", title: "Technische Nachvollziehbarkeit", text: "Domain Pack, Tools und Human Boundary öffnen.", mode: "technik" },
  { id: "wohngeld-vollstaendigkeit", title: "Auf Bürgerdienste übertragen", text: "Unterlagen und Inkonsistenzen prüfen, ohne Anspruchsentscheidung.", mode: "fach" },
  { id: "vergaberegel-schul-it", title: "GitLaw mit Fällen verbinden", text: "Regeländerungen auf konkrete laufende Projekte anwenden.", mode: "technik" },
];

async function showTourStep() {
  const step = tourSteps[tourIndex];
  mode = step.mode;
  $$(".modeToggle button").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  await selectCase(step.id, true);
  $("#tourStep").textContent = `SCHRITT ${tourIndex + 1} / ${tourSteps.length}`;
  $("#tourTitle").textContent = step.title;
  $("#tourText").textContent = step.text;
  $("#tourDock").style.setProperty("--tour-progress", `${((tourIndex + 1) / tourSteps.length) * 100}%`);
  $("#tourNext").textContent = tourIndex === tourSteps.length - 1 ? "Fertig" : "Weiter";
}

function startTour() {
  tourIndex = 0;
  $("#tourDock").classList.add("open");
  showTourStep();
}

function closeTour() {
  $("#tourDock").classList.remove("open");
}

function updateScrollProgress() {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  const progress = max > 0 ? (window.scrollY / max) * 100 : 0;
  $("#scrollProgress i").style.width = `${progress}%`;
}

$$(".modeToggle button").forEach((button) => button.addEventListener("click", () => {
  mode = button.dataset.mode;
  $$(".modeToggle button").forEach((item) => item.classList.toggle("active", item === button));
  renderMode();
}));
$("#askBtn").addEventListener("click", ask);
$("#question").addEventListener("keydown", (event) => { if (event.key === "Enter") ask(); });
$("#modalClose").addEventListener("click", () => $("#modal").classList.remove("open"));
$("#modal").addEventListener("click", (event) => { if (event.target === $("#modal")) $("#modal").classList.remove("open"); });
$("#tourStart").addEventListener("click", startTour);
$("#tourClose").addEventListener("click", closeTour);
$("#tourNext").addEventListener("click", () => {
  if (tourIndex === tourSteps.length - 1) return closeTour();
  tourIndex += 1;
  showTourStep();
});
window.addEventListener("scroll", updateScrollProgress, { passive: true });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeTour();
    $("#modal").classList.remove("open");
  }
});

(async () => {
  try {
    const health = await getJSON(`${API}/api/health`);
    $("#health").classList.add("ok");
    $("#health span").textContent = `Live Backend · ${health.version}`;
  } catch {
    $("#health span").textContent = "Demo mit Fallback";
  }
  try {
    cases = await getJSON(`${API}/api/v5/cases`);
  } catch {
    cases = fallbackCases;
  }
  renderCases();
  await selectCase(currentId);
  updateScrollProgress();
})();
