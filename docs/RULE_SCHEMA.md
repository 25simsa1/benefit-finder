# Rule file schema

Every program is one YAML file under `src/benefit_finder/rules/`. Federal
rules live in `federal/`, state rules in `states/<state>/`. The loader
rejects unknown top-level keys, so stick to this schema exactly. See
`federal/snap.yaml` and `federal/eitc.yaml` for worked examples.

## Required keys

| Key | Type | Meaning |
|---|---|---|
| `id` | str | unique slug, lowercase snake_case |
| `name` | str | display name |
| `category` | enum | `food` `health` `utilities` `communications` `tax_credit` `education` `housing` `cash` |
| `jurisdiction` | enum | `federal` `state` `county` |
| `description` | str | 2 to 4 sentences, what the program is |
| `income` | map | income test, see below |
| `value` | map | estimated annual value, see below |
| `next_step` | str | one or two sentences, the concrete next action |
| `application_url` | str | where to apply |
| `documents` | list[str] | documents checklist for the application |
| `source_url` | str | official page the limits came from |
| `last_verified` | ISO date | when the numbers were last checked |

## Optional keys

| Key | Default | Meaning |
|---|---|---|
| `states` | `[]` | required for state/county rules, e.g. `[KS]` |
| `household_size_basis` | `all` | `all` `snap` `tax` `fafsa`. Which counting rule sizes the household for the income test |
| `conditions` | `[]` | non-income eligibility conditions, see below |
| `conditions_mode` | `all` | `all` (every condition must pass) or `any` (one suffices) |
| `categorical_flags` | `[]` | profile flags that bypass the income test, e.g. `[receives_snap]` |
| `borderline_margin_pct` | `10` | income up to limit x (1 + margin/100) yields `borderline` instead of `no` |
| `confidence` | `screen` | `screen` caps a passing verdict at `likely`; `definitive` allows `yes` (use only for computed tax credits) |
| `verdict_cap` | none | `likely` or `borderline`, downgrades passing verdicts (use `borderline` when qualifying needs an action the profile cannot confirm, like making retirement contributions) |
| `skip_if_already_enrolled` | none | a profile flag; when set the program reports `enrolled` |
| `notes` | `""` | caveats, shown in the report fine print for this program |

## income

```yaml
income: {type: none}                                   # no income test
income: {type: fpl_percent, limit_pct: 130, measure: gross_annual}
income: {type: fpl_percent, limit_pct: 400, min_pct: 100}   # window (ACA)
income: {type: fixed, amount: 30615}
income: {type: fixed_by_size, amounts: {1: 20000, 2: 27000}, per_additional: 7000}
income: {type: fixed_by_filing_status, amounts: {mfj: 79000, hoh: 59250, single: 39500}}
```

`measure` is informational. AGI from the profile is compared against the
limit either way.

## value (annual unless `period: month`)

```yaml
value: {type: fixed, amount: 111}
value: {type: range, min: 300, max: 1500, note: One annual payment.}
value: {type: per_member, amount: 120, member_filter: {age_min: 5, age_max: 17}}
value: {type: builtin, name: eitc}    # builtins are eitc, ctc_actc, savers_credit, snap
value: {type: none}
```

## conditions

```yaml
conditions:
  - type: min_members_matching
    count: 1
    member_filter: {age_max: 4}
    describe: at least one child under 5
  - type: flag
    flag: pregnant_member
    equals: true
  - type: housing_status
    equals: own
  - type: income_drop_min_pct
    pct: 25
  - type: builtin_value_positive
    name: eitc
  - type: any_of
    conditions:
      - {type: min_members_matching, count: 1, member_filter: {age_min: 55}}
      - {type: min_members_matching, count: 1, member_filter: {disabled: true}}
```

`member_filter` keys are `age_min`, `age_max`, `relationship`, `student`
(`k12`/`college`/`none`), `income_type` (`w2`/`1099`/`none`), `disabled`,
`employed`. Scalar values match exactly, list values mean membership.
`describe` is optional and becomes the human-readable reason text.
Profile flags are `pregnant_member`, `veteran`, `recent_job_loss`,
`college_student_living_away`, `receives_snap`, `receives_medicaid`.

## Style

Prose fields (description, next_step, notes, describe, value note) use
plain sentences. No em dashes and no colons inside prose strings. Cite
real, current program parameters and set `last_verified` to the date the
source actually supports.

## Validate your file

```bash
.venv/bin/python -c "from benefit_finder.rules_loader import load_rule_file; print(load_rule_file('PATH').id, 'OK')"
```
