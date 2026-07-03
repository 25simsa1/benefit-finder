// App orchestrator: loads meta, wires the wizard, screens the profile,
// and switches between the intake, dashboard, and report views.
import * as api from "./api.js";
import { emptyProfile } from "./state.js";
import { toPayload } from "./state.js";
import { createWizard } from "./wizard.js";
import { renderDashboard } from "./dashboard.js";
import { renderReport } from "./report.js";

const views = {
  intake: document.getElementById("view-intake"),
  dashboard: document.getElementById("view-dashboard"),
  report: document.getElementById("view-report"),
};
const steps = Array.from(document.querySelectorAll(".stepper .step"));

let profile = emptyProfile();
let meta = null;
let wizard = null;
let lastScreen = null;

function showView(name) {
  for (const [key, node] of Object.entries(views)) node.hidden = key !== name;
  for (const btn of steps) {
    const active = btn.dataset.view === name;
    if (active) btn.setAttribute("aria-current", "true");
    else btn.removeAttribute("aria-current");
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setStepEnabled(name, enabled) {
  const btn = steps.find((b) => b.dataset.view === name);
  if (btn) btn.disabled = !enabled;
}

function replaceProfile(next) {
  profile = next;
  wizard = buildWizard();
  showView("intake");
}

function buildWizard() {
  return createWizard(views.intake, {
    meta,
    profile,
    onScreen: runScreen,
    onProfileReplaced: replaceProfile,
  });
}

// Re-screen with a possibly-different income. The rest of the profile
// (household, state, flags) is unchanged, so the dashboard's income
// control drives eligibility live. profile.agi is kept in sync so the
// wizard and report reflect whatever income was last chosen.
function screenFn(agi) {
  profile.agi = agi;
  return api.screen(toPayload(profile));
}

async function runScreen() {
  try {
    const data = await api.screen(toPayload(profile));
    lastScreen = data;
    renderDashboard(views.dashboard, data, { screenFn });
    setStepEnabled("dashboard", true);
    setStepEnabled("report", true);
    showView("dashboard");
  } catch (err) {
    alert("Could not screen this profile.\n\n" + err.message);
  }
}

async function runReport() {
  showView("report");
  views.report.innerHTML = '<p class="muted">Building report…</p>';
  try {
    const markdown = await api.report(toPayload(profile));
    renderReport(views.report, markdown);
  } catch (err) {
    views.report.innerHTML = "";
    alert("Could not build the report.\n\n" + err.message);
  }
}

function wireStepper() {
  for (const btn of steps) {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      const name = btn.dataset.view;
      if (name === "report") runReport();
      else if (name === "intake") { if (wizard) wizard.rerender(); showView("intake"); }
      else showView(name);
    });
  }
}

function paintMeta() {
  const disclaimer = document.getElementById("disclaimer");
  disclaimer.textContent = meta.disclaimer;
  const warn = document.getElementById("fpl-warning");
  if (meta.fpl_warning) { warn.textContent = meta.fpl_warning; warn.hidden = false; }
  const src = document.getElementById("footer-source");
  src.innerHTML =
    "Income limits use the " + meta.fpl_year + " Federal Poverty Level guidelines. " +
    'Source: <a href="' + meta.fpl_source_url + '" target="_blank" rel="noopener">HHS</a>.';
}

async function main() {
  try {
    meta = await api.getMeta();
  } catch (err) {
    views.intake.innerHTML = '<p class="error-text">Could not reach the server: ' + err.message + "</p>";
    return;
  }
  paintMeta();
  wireStepper();
  wizard = buildWizard();
  showView("intake");
}

main();
