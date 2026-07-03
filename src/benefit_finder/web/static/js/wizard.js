// Multi-step intake wizard bound to the shared profile state.
import { el, clear } from "./dom.js";
import { SAMPLE_PROFILE, emptyMember, normalizeProfile } from "./state.js";

const STEPS = ["Where you live", "Household members", "Income & housing", "Your situation"];

export function createWizard(root, { meta, profile, onScreen, onProfileReplaced }) {
  let step = 0;

  function select(name, options, value, onChange) {
    return el("select", { onchange: (e) => onChange(e.target.value) },
      options.map((o) =>
        el("option", { value: o.value, selected: o.value === value }, o.label)
      )
    );
  }

  function field(labelText, control, sub) {
    return el("div", { class: "field" }, [
      el("label", {}, [labelText, sub ? el("span", { class: "sub" }, " " + sub) : null]),
      control,
    ]);
  }

  function renderLocation() {
    return el("div", {}, [
      el("p", { class: "hint" }, "Benefit limits depend on your state and household."),
      field("State", el("input", {
        type: "text", maxlength: "2", placeholder: "e.g. KS", value: profile.state,
        oninput: (e) => { profile.state = e.target.value.toUpperCase(); },
        style: "text-transform:uppercase",
      }), "two-letter code"),
      el("div", { class: "row" }, [
        field("County", el("input", { type: "text", value: profile.county,
          oninput: (e) => { profile.county = e.target.value; } }), "optional"),
        field("ZIP code", el("input", { type: "text", value: profile.zip_code,
          oninput: (e) => { profile.zip_code = e.target.value; } }), "optional"),
      ]),
    ]);
  }

  function memberCard(member, index) {
    const head = el("div", { class: "member-head" }, [
      el("h3", {}, "Member " + (index + 1)),
      profile.members.length > 1
        ? el("button", { class: "btn danger small", type: "button",
            onclick: () => { profile.members.splice(index, 1); rerender(); } }, "Remove")
        : null,
    ]);
    return el("div", { class: "member-card" }, [
      head,
      el("div", { class: "row" }, [
        field("Age", el("input", { type: "number", min: "0", max: "130", value: String(member.age),
          oninput: (e) => { member.age = Number(e.target.value); } })),
        field("Relationship", select("relationship", meta.relationships, member.relationship,
          (v) => { member.relationship = v; })),
      ]),
      el("div", { class: "row" }, [
        field("Student", select("student", meta.student_statuses, member.student,
          (v) => { member.student = v; })),
        field("Income type", select("income_type", meta.income_types, member.income_type,
          (v) => { member.income_type = v; })),
      ]),
      el("label", { class: "check" }, [
        el("input", { type: "checkbox", checked: member.disabled,
          onchange: (e) => { member.disabled = e.target.checked; } }),
        "Has a disability",
      ]),
      el("label", { class: "check" }, [
        el("input", { type: "checkbox", checked: member.employed,
          onchange: (e) => { member.employed = e.target.checked; } }),
        "Currently employed",
      ]),
    ]);
  }

  function renderMembers() {
    return el("div", {}, [
      el("p", { class: "hint" }, "Add everyone who lives in the household and shares income."),
      el("div", {}, profile.members.map((m, i) => memberCard(m, i))),
      el("button", { class: "btn secondary", type: "button",
        onclick: () => { profile.members.push({ ...emptyMember() }); rerender(); } }, "+ Add member"),
    ]);
  }

  function renderIncome() {
    return el("div", {}, [
      el("p", { class: "hint" }, "Use adjusted gross income (AGI) from your tax return, or your best estimate."),
      field("Annual household AGI", el("input", { type: "number", min: "0", value: String(profile.agi),
        oninput: (e) => { profile.agi = Number(e.target.value); } }), "this year"),
      field("Prior-year AGI", el("input", { type: "number", min: "0",
        value: profile.prior_year_agi == null ? "" : String(profile.prior_year_agi),
        oninput: (e) => { profile.prior_year_agi = e.target.value === "" ? null : Number(e.target.value); } }),
        "optional; a big drop unlocks extra help"),
      field("Housing", select("housing", meta.housing_statuses, profile.housing_status,
        (v) => { profile.housing_status = v; })),
      field("Monthly housing cost", el("input", { type: "number", min: "0",
        value: profile.monthly_housing_cost == null ? "" : String(profile.monthly_housing_cost),
        oninput: (e) => { profile.monthly_housing_cost = e.target.value === "" ? null : Number(e.target.value); } }),
        "optional"),
    ]);
  }

  function renderFlags() {
    return el("div", {}, [
      el("p", { class: "hint" }, "Check anything that applies. Each can unlock specific programs."),
      el("div", {}, meta.flags.map((f) =>
        el("label", { class: "check" }, [
          el("input", { type: "checkbox", checked: Boolean(profile.flags[f.name]),
            onchange: (e) => { profile.flags[f.name] = e.target.checked; } }),
          f.label,
        ])
      )),
    ]);
  }

  const renderers = [renderLocation, renderMembers, renderIncome, renderFlags];

  function validateStep() {
    if (step === 0 && (!profile.state || profile.state.length !== 2)) {
      return "Enter a two-letter state code.";
    }
    if (step === 1) {
      if (!profile.members.length) return "Add at least one household member.";
      if (profile.members.some((m) => !Number.isFinite(m.age) || m.age < 0)) {
        return "Every member needs a valid age.";
      }
    }
    if (step === 2 && (!Number.isFinite(profile.agi) || profile.agi < 0)) {
      return "Enter a household AGI of 0 or more.";
    }
    return null;
  }

  function toolbar() {
    const importInput = el("input", { type: "file", accept: "application/json", hidden: true,
      onchange: (e) => importFile(e.target.files[0]) });
    return el("div", { class: "toolbar" }, [
      el("button", { class: "btn ghost small", type: "button",
        onclick: () => { onProfileReplaced(normalizeProfile(SAMPLE_PROFILE)); } }, "Load sample family"),
      el("button", { class: "btn ghost small", type: "button", onclick: exportProfile }, "Export profile"),
      el("button", { class: "btn ghost small", type: "button", onclick: () => importInput.click() }, "Import profile"),
      importInput,
    ]);
  }

  function exportProfile() {
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "profile.json" });
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  async function importFile(file) {
    if (!file) return;
    try {
      const obj = JSON.parse(await file.text());
      onProfileReplaced(normalizeProfile(obj));
    } catch {
      alert("That file is not valid JSON.");
    }
  }

  function rerender() {
    clear(root);
    const errorSlot = el("p", { class: "error-text" });
    const panel = el("div", { class: "card step-panel" }, [
      el("h2", {}, "Step " + (step + 1) + " of " + STEPS.length + ": " + STEPS[step]),
      renderers[step](),
      errorSlot,
      el("div", { class: "actions" }, [
        el("button", { class: "btn secondary", type: "button", disabled: step === 0,
          onclick: () => { step = Math.max(0, step - 1); rerender(); } }, "Back"),
        step < STEPS.length - 1
          ? el("button", { class: "btn", type: "button", onclick: () => {
              const err = validateStep();
              if (err) { errorSlot.textContent = err; return; }
              step++; rerender();
            } }, "Next")
          : el("button", { class: "btn", type: "button", onclick: () => {
              const err = validateStep();
              if (err) { errorSlot.textContent = err; return; }
              onScreen();
            } }, "See results"),
      ]),
    ]);
    root.append(panel, toolbar());
  }

  rerender();
  return { rerender };
}
