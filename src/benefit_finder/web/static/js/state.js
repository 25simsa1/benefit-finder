// In-memory profile state. Nothing is persisted automatically; the user
// exports/imports JSON to save a profile. This matches the CLI's
// profile.json schema exactly so files are interchangeable.

export const SAMPLE_PROFILE = {
  state: "KS",
  county: "Sedgwick",
  zip_code: "67214",
  members: [
    { age: 38, relationship: "self", student: "none", disabled: false, employed: true, income_type: "w2" },
    { age: 36, relationship: "spouse", student: "none", disabled: false, employed: true, income_type: "w2" },
    { age: 16, relationship: "child", student: "k12", disabled: false, employed: false, income_type: "none" },
    { age: 11, relationship: "child", student: "k12", disabled: false, employed: false, income_type: "none" },
    { age: 4, relationship: "child", student: "none", disabled: false, employed: false, income_type: "none" },
  ],
  agi: 45000,
  prior_year_agi: 62000,
  housing_status: "rent",
  monthly_housing_cost: 1150,
  flags: {},
};

export function emptyMember() {
  return { age: 0, relationship: "self", student: "none", disabled: false, employed: false, income_type: "none" };
}

export function emptyProfile() {
  return {
    state: "",
    county: "",
    zip_code: "",
    members: [{ ...emptyMember() }],
    agi: 0,
    prior_year_agi: null,
    housing_status: "rent",
    monthly_housing_cost: null,
    flags: {},
  };
}

// Coerce an imported object into our shape, dropping unknown keys so a
// slightly-off file still loads. Server-side validation is the backstop.
export function normalizeProfile(obj) {
  const base = emptyProfile();
  if (!obj || typeof obj !== "object") return base;
  base.state = String(obj.state || "").toUpperCase().slice(0, 2);
  base.county = String(obj.county || "");
  base.zip_code = String(obj.zip_code ?? obj.zip ?? "");
  base.housing_status = obj.housing_status === "own" ? "own" : "rent";
  base.agi = Number(obj.agi) || 0;
  base.prior_year_agi = obj.prior_year_agi == null ? null : Number(obj.prior_year_agi);
  base.monthly_housing_cost = obj.monthly_housing_cost == null ? null : Number(obj.monthly_housing_cost);
  base.flags = {};
  if (obj.flags && typeof obj.flags === "object") {
    for (const [k, v] of Object.entries(obj.flags)) base.flags[k] = Boolean(v);
  }
  if (Array.isArray(obj.members) && obj.members.length) {
    base.members = obj.members.map((m) => ({
      age: Number(m.age) || 0,
      relationship: String(m.relationship || "self"),
      student: String(m.student || "none"),
      disabled: Boolean(m.disabled),
      employed: Boolean(m.employed),
      income_type: String(m.income_type || "none"),
    }));
  }
  return base;
}

// Build the exact payload the API expects (drop empty optional fields as null).
export function toPayload(profile) {
  return {
    state: profile.state,
    county: profile.county || "",
    zip_code: profile.zip_code || "",
    members: profile.members,
    agi: Number(profile.agi) || 0,
    prior_year_agi: profile.prior_year_agi === null || profile.prior_year_agi === ""
      ? null : Number(profile.prior_year_agi),
    monthly_housing_cost: profile.monthly_housing_cost === null || profile.monthly_housing_cost === ""
      ? null : Number(profile.monthly_housing_cost),
    housing_status: profile.housing_status,
    flags: profile.flags,
  };
}
