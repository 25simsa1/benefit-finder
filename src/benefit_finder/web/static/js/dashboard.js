// Results dashboard. An income control at the top re-screens live as the
// user types or drags, so eligibility is driven by their income (never a
// fixed value). Below it, a results section shows the total banner,
// special situations, and grouped expandable program cards from
// /api/screen, sorted by estimated annual value.
import { el, clear, money } from "./dom.js";

const SLIDER_MAX = 250000;
const SLIDER_STEP = 1000;

function chip(verdict) {
  return el("span", { class: "chip " + verdict }, verdict);
}

function programCard(ev) {
  const head = el("div", { class: "prog-head" }, [
    chip(ev.verdict),
    el("span", { class: "prog-title" }, ev.program),
    el("span", { class: "prog-value" }, ev.estimated_value ? ev.estimated_value.formatted : "—"),
    el("span", { class: "chev" }, "›"),
  ]);

  const body = el("div", { class: "prog-body" });
  body.append(el("p", { class: "desc" }, ev.description));

  if (ev.size_basis_explanation) {
    body.append(el("div", { class: "nuance" }, [
      el("strong", {}, "Household-size note. "), ev.size_basis_explanation,
    ]));
  }

  body.append(el("h4", {}, "Why this verdict"));
  body.append(el("ul", { class: "reasons" }, ev.reasons.map((r) => el("li", {}, r))));

  if (ev.estimated_value && ev.estimated_value.note) {
    body.append(el("h4", {}, "About this estimate"));
    body.append(el("p", { class: "muted" }, ev.estimated_value.note));
  }

  if (ev.verdict !== "no") {
    body.append(el("h4", {}, "How to apply"));
    const apply = el("p", {}, [ev.next_step + " "]);
    if (ev.application_url) {
      apply.append(el("a", { class: "btn small", href: ev.application_url, target: "_blank", rel: "noopener" }, "Apply ↗"));
    }
    body.append(apply);

    if (ev.documents.length) {
      body.append(el("h4", {}, "Documents to gather"));
      body.append(el("ul", { class: "doc-list" }, ev.documents.map((d) => el("li", {}, d))));
    }
  }

  body.append(el("p", { class: "src" }, [
    "Source: ",
    el("a", { href: ev.source_url, target: "_blank", rel: "noopener" }, ev.source_url),
    " • last verified " + ev.last_verified,
  ]));

  const card = el("details", { class: "card prog" }, [
    el("summary", {}, head),
    body,
  ]);
  return card;
}

function renderResults(container, data) {
  clear(container);

  container.append(el("div", { class: "total-banner" }, [
    el("div", { class: "amount" },
      data.total_high > 0 ? money(data.total_low) + " to " + money(data.total_high) : "See details below"),
    el("div", { class: "sub" },
      data.total_high > 0
        ? "Estimated combined annual value of programs you likely qualify for at this income."
        : "No clear-cut matches at this income, but review the borderline programs below."),
  ]));

  if (data.special_situations.length) {
    const sit = el("div", { class: "situations" }, [el("h2", {}, "Special situations")]);
    for (const s of data.special_situations) {
      sit.append(el("div", { class: "sit" }, [el("h3", {}, s.title), el("p", {}, s.guidance)]));
    }
    container.append(sit);
  }

  const byGroup = new Map();
  for (const ev of data.evaluations) {
    if (!byGroup.has(ev.group)) byGroup.set(ev.group, []);
    byGroup.get(ev.group).push(ev);
  }
  for (const group of data.group_order) {
    const items = byGroup.get(group);
    if (!items || !items.length) continue;
    const section = el("div", { class: "group" }, [
      el("h2", {}, [group, el("span", { class: "count" }, items.length + " program" + (items.length > 1 ? "s" : ""))]),
    ]);
    for (const ev of items) section.append(programCard(ev));
    container.append(section);
  }
}

// The income control: number input + slider, kept in sync, that calls
// screenFn(agi) (debounced) and repaints the results in place.
function incomeControl(data, onIncome) {
  const num = el("input", {
    type: "number", min: "0", step: "100", class: "income-num",
    value: String(Math.round(data.agi)), "aria-label": "Annual household income",
  });
  const slider = el("input", {
    type: "range", min: "0", max: String(SLIDER_MAX), step: String(SLIDER_STEP),
    value: String(Math.min(Math.round(data.agi), SLIDER_MAX)),
    "aria-label": "Adjust annual household income",
  });
  const fplLine = el("p", { class: "fpl-line muted" });

  function paintContext(d) {
    fplLine.textContent =
      "About " + Math.round(d.income_percent_of_fpl) + "% of the " + d.fpl_year +
      " federal poverty level for a household of " + d.household_size + ".";
  }

  const control = el("div", { class: "card income-control" }, [
    el("div", { class: "label" }, "Your annual household income"),
    el("div", { class: "income-value" }, [
      el("span", { class: "dollar" }, "$"),
      num,
      el("span", { class: "per" }, "/ year"),
    ]),
    slider,
    el("div", { class: "ticks" }, [el("span", {}, "$0"), el("span", {}, money(SLIDER_MAX) + "+")]),
    fplLine,
    el("p", { class: "hint" }, "Type or drag to see how your eligibility changes. Household, state, and situation come from your profile."),
  ]);

  function apply(value, { syncNum = true, syncSlider = true } = {}) {
    let agi = Number(value);
    if (!Number.isFinite(agi) || agi < 0) agi = 0;
    if (syncNum) num.value = String(Math.round(agi));
    if (syncSlider) slider.value = String(Math.min(Math.round(agi), SLIDER_MAX));
    onIncome(agi, paintContext);
  }

  slider.addEventListener("input", (e) => apply(e.target.value, { syncSlider: false }));
  num.addEventListener("input", (e) => apply(e.target.value, { syncNum: false }));

  paintContext(data);
  return control;
}

export function renderDashboard(root, initialData, { screenFn }) {
  clear(root);

  const results = el("div", { class: "dash-results" });
  renderResults(results, initialData);

  let seq = 0;
  let timer = null;

  function reScreen(agi, paintContext) {
    clearTimeout(timer);
    const mySeq = ++seq;
    timer = setTimeout(async () => {
      try {
        const data = await screenFn(agi);
        if (mySeq !== seq) return; // a newer change superseded this one
        paintContext(data);
        renderResults(results, data);
      } catch (err) {
        if (mySeq !== seq) return;
        clear(results);
        results.append(el("p", { class: "error-text" }, "Could not screen this income: " + err.message));
      }
    }, 160);
  }

  const control = incomeControl(initialData, reScreen);
  root.append(control, results);
}
