# REF-LC baseline validation — corrected least-cost reference (1 node, LC-182h)

**Study:** PyPSA-RSA gas-to-power transition and stranded-asset risk, South Africa 2025–2050
**Scenario:** `REF-LC` (`scenarios/Coal_Flexibilisation/scenarios_to_run.xlsx::scenario_definition`)
**Run validated:** 2026-10-22 19:17–19:20 (SAST), forced 5-job Snakemake workflow, 8 threads
**Report date:** 2026-10-26 · **Author:** Matthew Gabin (analysis assisted by Claude Code)
**Status:** read-only validation; no model inputs, scripts or results were changed in preparing this report.

**Evidence tags used throughout**

| Tag | Meaning |
|---|---|
| **[CONFIRMED]** | Read directly from model code, input workbooks, solver output or `solved.nc`. |
| **[ASSUMPTION]** | An input assumption or an interpretive judgement that is not itself tested here. |
| **[VALIDATE]** | A plausible inference or open question that needs a targeted test or data check before being relied on. |

Unit convention: the solved network stores all monetary quantities in **thousand ZAR (kZAR)**. `prepare_and_solve_network.py:561` calls `scale_costs(n, 1e3)` and never reverses it before export. Unless stated otherwise, power is in MW, energy in MWh/TWh, and costs in kZAR or bn ZAR (1 bn ZAR = 10⁶ kZAR).

---

## 1. Purpose and status

This report establishes whether the corrected REF-LC run is a defensible least-cost reference for the gas-policy scenarios (POL-3GW, POL-6GW, POL-16GW). It documents:
- the configuration;
- the evidence of solver optimality;
- the numerical results;
- the differences from the original (pre-correction) REF-LC run;
- known technology-representation and temporal-aggregation limitations.

**Status: completed; Gurobi terminated OPTIMAL (barrier, no crossover). The objective and termination status were recovered from preserved console output; the final primal–dual gap/bound was not preserved.** [CONFIRMED, see §3]

Headline results (corrected run):
- The objective is 2.674 × 10⁹ kZAR (≈ R2.67 trillion, present value at 9.2%).
- The reserve margin binds in every active period (2030–2050), with retired coal correctly deducted.
- There is no material load shedding.
- ≈ 26.9 GW of coal is retired endogenously in 2030 and essentially all coal by 2035.
- ≈ 42.8 GW of OCGT-class capacity is active by 2050, but with very low utilisation.

Two structural issues limit how far these results can be interpreted: degenerate OCGT technology options (§11) and LC-182h block averaging (§4, §12). They must be addressed or explicitly scoped before policy runs (§13).

---

## 2. Model configuration and scenario assumptions

### 2.1 Workflow and environment

| Item | Value |
|---|---|
| Pipeline | `build_topology → base_network → add_electricity → prepare_and_solve_network → plot_network` (`Snakefile`) |
| Scenario folder | `config.yaml::scenarios.working_folder = Coal_Flexibilisation` |
| Software | conda env `pypsa-rsa`: PyPSA 0.35.2, linopy 0.5.8, pandas 2.2.3; Gurobi (academic licence) |
| Formulation | Single LP, multi-period perfect foresight (`multi_investment_periods=True`); linearised unit commitment for committable plant |
| Spatial | 1 node (`RSA`) |
| Temporal | `options = LC-182h`: 182-hour block averaging (see §4) |
| Investment periods | 2025, 2030, 2035, 2040, 2045, 2050 |
| Discount rate | 9.2% (`global_discount_rate`) |
| Currency conversion | USD→ZAR 18.24; EUR→ZAR 17.83 (`config.yaml:193–194`) |
| Cost noise | `noisy_costs: True`, `random_seed: 174` (reproducible random perturbation of marginal costs) |

### 2.2 REF-LC scenario labels (as loaded by `_helpers.load_scenario_definition`)

| Column | Label | Column | Label |
|---|---|---|---|
| `regions` | 1 | `extendable_active` | BASE |
| `options` | LC-182h | `extendable_parameters` | BASE_PMR1b |
| `simulation_years` | 2025, 2030, …, 2050 | `extendable_fuel_prices` | BASE_PMR1b |
| `transmission_grid` | existing+tdp | `extendable_emissions` | BASE |
| `weather` | W_P50 | `extendable_min/max_total` | UNC / UNC |
| `load_trajectory` | LOWDelEVs | `extendable_min/max_annual` | UNC / UNC |
| `fixed_conventional` | BASE_PMR1b | `aux_stg_feed` | DIESEL_LNG |
| `fixed_fuel_prices` | BASE_PMR1b | `operational_limits` | **NO_GAS_FLOOR** |
| `fixed_emissions` | BASE | `operational_reserves` | BASE (inactive; call commented out) |
| `phased_decom` | DELAYED_ESKOM_2035 | `reserve_margin` | RES_MRGN_10 |
| `unit_committment` | 1 | `capacity_credits` | BASE2 |
| `endogenous_coal_decom` | 1 | `carbon_tax` | CT_2050 |
| `dispatch_coal_flex` | SL_0 | `carbon_constraints` / `co2_cap` | none / none |
| `override_coal_msl` | 0.65 | `annual_availability` | EAF_60 |
| `global_discount_rate` | 0.092 | `solver` | gurobi |

Only REF-LC has a truthy `run_scenario` in the current workbook. [CONFIRMED]

### 2.3 Changes relative to the original REF-LC run, and why

| # | Change | Where | Reason |
|---|---|---|---|
| 1 | `operational_limits`: `NO_MIN_GAS` → `NO_GAS_FLOOR` | `scenarios_to_run.xlsx::scenario_definition`, REF-LC row; new label in `sub_scenarios/operational_constraints.xlsx::operational_constraints` | `NO_MIN_GAS` imposes monthly **minimum** capacity factors of 40% on new `ocgt_gas` (and H2-conversion OCGTs) and 30% on all `ccgt_steam` from 2030. Despite its name it is a take-or-pay obligation. These floors were inherited from an earlier IRP-review setup without documented rationale. They penalise new gas in a least-cost reference. `NO_GAS_FLOOR` keeps the four other rows of `NO_MIN_GAS` unchanged (nuclear hourly min CF, rmippp monthly min CF, sasol_coal and sasol_gas annual max output) and drops the gas floors. `NO_MIN_GAS` itself is unchanged (verified identical to HEAD, including cached formula values) because all other scenario rows, including the collaborator's P0/P1 rows, still use it. [CONFIRMED] |
| 2 | Reserve-margin correction | `scripts/custom_constraints.py:324` (`# MG adjusted`) | The original `if coal_decom != 0: lhs = lhs - coal_decom` never executed. For a linopy expression, the comparison `coal_decom != 0` evaluates as False, so the subtraction was skipped. Endogenously retired coal therefore kept its capacity credit. The deduction is now unconditional. Verified with an offline linopy structural check before the run, and ex post in §5. [CONFIRMED] |
| 3 | `regions`: 10 → 1 | REF-LC row | Development at 1 node because of workstation memory. At 1 node the 10-node defects in the checklist (annual build limits skipped, CCGT-steam bus query) do not apply. [CONFIRMED] |
| — | `options = LC-182h` | REF-LC row | Unchanged vs HEAD; retained for development runs. |

The original REF-LC run (2026-10-06) is preserved under `backups/REF-LC_LC-182h_pre-correction_2026-10-22/`. All 17 files pass `sha256sum -c MANIFEST.sha256` (re-verified 2026-10-26). [CONFIRMED]

### 2.4 Assumptions that remain unchanged [ASSUMPTION]
- **Reserve margin:** 10% above peak demand, active from 2030 (`reserve_margin.xlsx::reserve_margin::RES_MRGN_10`).
- **Capacity credits** (`reserve_margin.xlsx::capacity_credits::BASE2`):
  - coal 0.53; nuclear, OCGT (gas/diesel/H2_40–50), ccgt_steam, PHS and biomass 1.0;
  - solar PV 0; wind 0.10; CSP 0.5; batteries 0.25/0.5/0.75 for 1/4/8 h;
  - `ocgt_gas_h2_55/60` absent, hence zero.
- **Coal retirement:** the `DELAYED_ESKOM_2035` schedule is an exogenous floor. Endogenous retirement is allowed from 2030 (`config.yaml: endogenous_decomssioning_start_year = 2030`), and the floor applies as `>=` from then.
- **Carbon tax** `CT_2050` (R/tCO₂e): 236 (2025), 462 (2030), 894 (2035), 1,326 (2040), 1,757 (2045), 2,189 (2050). It is added to marginal and stand-by costs.
- **Fuel prices** `BASE_PMR1b` (R/GJ):
  - new `ocgt_gas` 216 → 239;
  - new `ocgt_diesel` 389 → 424.
- **Gas technology:** 30-year lifetime; overnight build; no endogenous early retirement for new gas.
- **CCGT coupling:** steam output ≤ 0.427 × output of feeding OCGT-class units (`config.yaml:95`, `aux_stg_feed::DIESEL_LNG`).
- **Solver settings** (`config.yaml::solver.gurobi`): Method 2 (barrier), Crossover 0, BarConvTol 1e-5, AggFill 0, PreDual 0. Threads is overridden to 8 by `snakemake.threads` (`prepare_and_solve_network.py:545`).

### 2.5 Repository state
- The run used **uncommitted** working-tree changes on `master` (HEAD `6f920cf`).
- Modified relative to HEAD: `scenarios_to_run.xlsx`, `operational_constraints.xlsx`, `scripts/custom_constraints.py`, and `gurobi.log` (licence-probe appends only).
- All input mtimes (≤ 18:57 on 2026-10-22) predate the run start (19:17).
- The scenario workbook also contains a pre-existing, unrelated uncommitted value on the POL-6GW row (`transmission_grid = "LC-2190h"`). It does not affect REF-LC.

---

## 3. Solver status and objective

### 3.1 Three distinct layers of evidence

| Layer | Evidence | Result |
|---|---|---|
| Snakemake | `.snakemake/log/2026-10-22T191716.579753.snakemake.log` | 5 of 5 jobs completed. `prepare_and_solve_network` 19:19:08 → 19:20:11. No locks or incomplete markers remain. Snakemake success alone only proves the script exited without error. [CONFIRMED] |
| PyPSA / linopy | Console output (recovered, see below); `solved.nc` | `Status: ok`, `Termination condition: optimal`. PyPSA assigns a solution only when status is `ok` (`pypsa/optimization/optimize.py:568`). `solved.nc` contains a full solution: objective set, no NaNs in dispatch or prices. Note that linopy's `ok` also covers `suboptimal`, `imprecise` and limit terminations, so the termination line is the decisive evidence. [CONFIRMED] |
| Gurobi | Console output (recovered) | `Barrier solved model in 41 iterations and 5.74 seconds (2.39 work units)`; `Optimal objective 2.67400446e+09` at 19:20:03. Matches `n.objective = 2,674,004,460.5` exactly. [CONFIRMED] |

**Provenance of the console output.**
- Snakemake has no `log:` directive for the solve rule. `gurobi.log` was last written at 19:17:14, by Snakemake's start-up licence probe, not by the solve.
- The console output was captured to a temporary file during the session. That file was lost when the workstation restarted.
- A filtered copy of it survives in the Claude Code session transcript (`~/.claude/projects/-home-matthew-EnergyModels-pypsa-rsa-agatha/8aa323d3-8701-42de-af0a-5ca8502aa1b2.jsonl`).

**Not recovered:**
- the barrier iteration table (final primal/dual objectives and residuals);
- problem dimensions;
- an explicit gap or bound.

For a barrier solve, "optimal" means Gurobi's convergence criteria were met: relative primal–dual gap ≤ BarConvTol (1e-5, i.e. ≲ 2.7 × 10⁴ kZAR on this objective) and primal/dual feasibility within the default tolerances. [VALIDATE: inferred from Gurobi semantics, not read from the log]

Because Crossover = 0, the solution is an interior point of the optimal face, not a basic (vertex) solution. This matters for degenerate technology choices (§11). [CONFIRMED]

### 3.2 Objective

| Quantity | Corrected | Pre-correction | Δ |
|---|---|---|---|
| `n.objective` (kZAR, PV) | 2,674,004,460 | 2,588,455,007 | +85.5 × 10⁶ (+3.3%) |
| `n.objective_constant` (kZAR) | 24,349,277 | 24,349,277 | 0 |

The objective is the discounted sum of annualised investment, fixed and variable costs over the period weightings (§4), net of coal-retirement FOM savings, in kZAR.

Reporting note [CONFIRMED in code; VALIDATE impact]:
- In `add_coal_decom` (`prepare_and_solve_network.py:346–353`), the retirement constant is added to the objective as `-1 * object_const`. The accompanying comment suggests the opposite sign was intended.
- This shifts the reported objective by a constant. It does not affect decisions, and it is identical in both runs (`objective_constant` is unchanged).
- Absolute objective values should not be quoted as total system cost until this is confirmed.

---

## 4. Temporal structure and weighting [CONFIRMED]

| Period | Snapshots | Snapshot weights (h) | Hours represented | Hours dropped | Period length (yr) | Objective weight (Σ discount factors) |
|---|---|---|---|---|---|---|
| 2025 | 49 | 182 (+ remainder) | 8,760 | 0 | 5 | 4.2255 |
| 2030 | 48 | 47 × 182, 1 × 168 | 8,722 | 38 | 5 | 2.7213 |
| 2035 | 48 | 182 / 168 | 8,684 | 76 | 5 | 1.7525 |
| 2040 | 48 | 182 / 168 | 8,646 | 114 | 5 | 1.1286 |
| 2045 | 48 | 182 / 168 | 8,632 | 128 | 5 | 0.7268 |
| 2050 | 48 | 182 / 168 | 8,594 | 166 | **50** | 1.2987 |

- `LC-182h` averages the hourly profiles over consecutive 182-hour blocks (≈ 7.6 days). It does not use representative days.
- Within each block, load, solar and wind are replaced by their means. In 2030 the solar PV `p_max_pu` ranges from 0.22 to 0.42 and **never reaches zero**, and block-mean load ranges from 23.1 to 28.3 GW.
- **The model therefore contains no diurnal cycle.** This is the single most important limitation for interpreting gas utilisation (§12).
- Hours dropped are those that do not fill a complete block at the end of each year (`average_every_nhours`).
- The final period is weighted 50 years (`base_network.py:124`), which gives 2050 operating conditions a large terminal weight.

---

## 5. Reserve-margin compliance

Definition (`custom_constraints.py:256–325`):

Σ credit × firm capacity of active assets − 0.53 × retired existing coal  ≥  (1 + 10%) × peak block-mean load.

The table below was recomputed ex post from `solved.nc` and `outputs/decom_status.csv`. Capacity credits are from `BASE2`; "gross firm" is before the retired-coal deduction.

### 5.1 Corrected run [CONFIRMED]

| Period | RM active | Peak (MW) | Requirement (MW) | Gross firm (MW) | Retired coal (MW, cumulative) | Net firm (MW) | Net slack (MW) |
|---|---|---|---|---|---|---|---|
| 2025 | no | 27,288 | 30,017 | 31,206 | 0 | 31,206 | +1,189 |
| 2030 | yes | 28,342 | 31,176 | 45,441 | 26,915 | 31,176 | **+0.014** |
| 2035 | yes | 31,008 | 34,108 | 48,442 | 27,045 | 34,108 | **+0.017** |
| 2040 | yes | 34,737 | 38,210 | 52,544 | 27,045 | 38,210 | **+0.031** |
| 2045 | yes | 39,855 | 43,840 | 50,437 | 12,447 | 43,840 | **+0.043** |
| 2050 | yes | 45,533 | 50,087 | 56,684 | 12,447 | 50,087 | **+0.048** |

The constraint binds in every active period and is satisfied net of retired coal. The tiny positive slacks are consistent with an interior-point solution.

### 5.2 Pre-correction run [CONFIRMED]

| Period | Gross firm (MW) | Retired coal (MW) | Net firm (MW) | Net slack (MW) | Gross slack (MW) |
|---|---|---|---|---|---|
| 2030 | 31,176 | 27,662 | 16,516 | **−14,661** | +0.0001 |
| 2035 | 34,108 | 27,045 | 19,774 | **−14,334** | +0.0001 |
| 2040 | 38,210 | 27,045 | 23,876 | **−14,334** | +0.0002 |
| 2045 | 43,840 | 12,447 | 37,243 | **−6,597** | +0.0007 |
| 2050 | 50,087 | 12,447 | 43,490 | **−6,597** | +0.0011 |

The original run met the reserve margin only because retired coal was still credited. Measured correctly, it was short by 6.6–14.7 GW of firm capacity in every active period. This confirms the bug and its correction.

[VALIDATE] The requirement uses the peak of the 182-h block-mean load (28.3 GW in 2030), not the hourly peak. The true firm-capacity requirement is therefore likely understated (§12).

---

## 6. Load shedding and numerical tolerances [CONFIRMED]

| | Corrected | Pre-correction |
|---|---|---|
| Load shedding, total energy (all periods, MWh) | 0.0017 | 0.00004 |
| Load shedding, maximum (MW) | 0.00007 (2025) | 0.000002 |
| NaN in dispatch / prices | none | none |

- Load shedding is numerically zero: values of this size are barrier residuals, not involuntary curtailment.
- Retirement fractions of order 10⁻⁶ (e.g. Medupi 2030, Kusile 2050) and sub-MW capacities of non-built technologies are likewise solver noise.
- Reporting thresholds of ≥ 1 MW and ≥ 10⁻³ (fractions) are used below.

---

## 7. Capacity

### 7.1 New natural-gas / OCGT-class / CCGT build by vintage (MW) [CONFIRMED]

Corrected run:

| Carrier | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| ocgt_gas | 0 | 2,865 | 790 | 1,089 | 4,254 | 1,750 |
| ccgt_steam | 0 | 1,680 | 1,424 | 170 | 0 | 1,083 |
| ocgt_gas_h2_40 | 0 | 2,837 | 2,690 | 916 | 527 | 1,612 |
| ocgt_gas_h2_45 | 0 | 2,841 | 1,541 | 2,644 | 527 | 1,612 |
| ocgt_gas_h2_50 | 0 | 3,959 | 701 | 927 | 535 | 1,612 |
| ocgt_gas_h2_55 / _60 | 0 | 0 | 0 | 0 | 0 | 0 |

Pre-correction run: no new `ocgt_gas` or `ccgt_steam`. Its H2-conversion OCGT builds were h2_40 5,769 (2040), 3,526 (2045), 2,308 (2050); h2_45 3,544 (2045), 2,332 (2050); h2_50 2,331 (2050).

### 7.2 Active capacity by period (GW, existing + new) [CONFIRMED]

| Carrier | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| coal (nameplate of plants within lifetime)¹ | 41.4 | 36.0 | 27.0 | 27.0 | 12.4 | 12.4 |
| coal (net of endogenous retirement) | 41.4 | 9.1 | ≈0 | ≈0 | ≈0 | ≈0 |
| nuclear | 1.9 | 1.9 | 1.9 | 1.9 | 1.9 | 0.0 |
| ocgt_diesel (existing + new) | 3.4 | 5.9 | 6.6 | 5.4 | 5.9 | 6.5 |
| ocgt_gas (new) | 0.0 | 2.9 | 3.7 | 4.7 | 9.0 | 10.7 |
| ccgt_steam (new) | 0.0 | 1.7 | 3.1 | 3.3 | 3.3 | 4.4 |
| ocgt_gas_h2_40 / 45 / 50 (new) | 0.0 | 2.8 / 2.8 / 4.0 | 5.5 / 4.4 / 4.7 | 6.4 / 7.0 / 5.6 | 7.0 / 7.6 / 6.1 | 8.6 / 9.2 / 7.7 |
| **OCGT-class total** (gas + H2 + diesel) | 3.4 | 18.4 | 24.8 | 29.2 | 35.6 | 42.8 |
| solar_pv | 2.7 | 37.9 | 39.4 | 58.3 | 67.2 | 66.6 |
| solar_pv_low | 0.0 | 13.4 | 42.4 | 42.4 | 60.2 | 88.4 |
| wind (existing; no new build) | 4.3 | 4.3 | 3.5 | 2.1 | 0.0 | 0.0 |
| solar_csp | 0.6 | 0.6 | 0.6 | 0.6 | 0.5 | 0.1 |
| hydro / hydro_import / bioenergy | 0.7 / 1.8 / 0.2 | same | same | same | same | same |
| sasol_coal / sasol_gas / rmippp | 0.7 / 0.4 / 0.4 | 0.7 / 0.4 / 0.4 | 0 / 0.4 / 0.4 | 0 / 0 / 0.4 | 0 | 0 |
| new storage (battery, PHS) | 0 | 0 | 0 | 0 | 0 | 0 |

¹ PyPSA keeps retired coal at its nameplate `p_nom`. Endogenous retirement acts through the `Generator-p_nom_ret` variable, which reduces unit-commitment status and the reserve-margin credit (§9).

---

## 8. Generation, capacity factors, emissions and system costs

### 8.1 Generation (TWh/yr) — corrected run [CONFIRMED]

| Carrier | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| coal | 170.3 | 41.0 | 0.3 | 0.0 | 0.0 | 0.0 |
| solar_pv + solar_pv_low | 6.1 | 132.8 | 199.1 | 238.2 | 290.2 | 350.3 |
| wind | 14.9 | 14.9 | 12.1 | 7.2 | 0.0 | 0.0 |
| nuclear | 15.2 | 14.6 | 14.5 | 14.4 | 14.4 | 0.0 |
| hydro_import / hydro | 10.1 / 1.8 | 10.1 / 1.8 | 10.1 / 1.8 | 10.0 / 1.8 | 10.0 / 1.8 | 10.0 / 1.8 |
| ocgt_gas | 0.0 | 0.1 | 0.5 | 0.9 | 6.2 | 6.5 |
| ocgt_gas_h2_40 / 45 / 50 | 0 | 0.1 / 0.1 / 6.4 | 6.9 / 2.6 / 0.2 | 0.0 / 6.7 / 0.6 | 0 / 0 / 0.4 | 0 |
| ccgt_steam | 0.0 | 2.8 | 4.3 | 3.3 | 2.8 | 2.8 |
| sasol_coal / rmippp / csp / bio / phs | 5.5 / 1.9 / 2.0 / 0.9 / 0.1 | 5.4 / 1.9 / 2.0 / 1.0 / 0.3 | 0 / 1.9 / 2.0 / 0.9 / 0.3 | 0 / 1.9 / 2.0 / 0.9 / 0.2 | 0 / 0 / 1.5 / 0.9 / 0.2 | 0 / 0 / 0.3 / 0.9 / 0.4 |
| **Load** | 228.5 | 234.5 | 256.8 | 287.7 | 327.4 | 371.9 |

By 2050 solar supplies ≈ 94% of energy. VRE curtailment rises from 4.5% (2025) to 19% (2045–2050).

### 8.2 Gas capacity factors (energy / (active capacity × represented hours)) [CONFIRMED]

| Carrier | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|
| ocgt_gas (new) | 0.2% | 1.5% | 2.2% | 7.9% | 7.0% |
| ccgt_steam (new) | 19.3% | 16.1% | 11.8% | 9.9% | 7.4% |
| ocgt_gas_h2_40 | 0.3% | 14.4% | 0.0% | 0.0% | 0.0% |
| ocgt_gas_h2_45 | 0.3% | 6.8% | 11.1% | 0.0% | 0.0% |
| ocgt_gas_h2_50 | 18.5% | 0.6% | 1.3% | 0.7% | 0.0% |
| existing ocgt_diesel | 0.0% | 0.0% | 0.0% | 0.0% | — |
| existing sasol_gas | 0.0% | 0.0% | — | — | — |

- The **minimum** block-level CF of every built new gas unit is 0 in every period. The inherited 40%/30% minimum-generation floors are therefore absent, as intended. [CONFIRMED]
- **Peaker utilisation.** OCGT-class installed capacity versus the maximum simultaneous OCGT-class output in any block:

| | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|
| Installed (GW) | 18.4 | 24.8 | 29.2 | 35.6 | 42.8 |
| Max output (GW) | 3.5 | 4.8 | 7.0 | 4.5 | 5.9 |

  More than 80% of OCGT-class capacity is never dispatched at LC-182h. It is held only to satisfy the reserve margin (§11, §12).

### 8.3 CO₂ emissions (Mt/yr, generation × `outputs/generator_emissions.csv`, excluding stand-by emissions) [CONFIRMED]

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| Corrected | 198.7 | 51.5 | 7.0 | 5.4 | 4.3 | 4.2 |
| Pre-correction | 198.7 | 41.9 | 1.9 | 0.0 | 0.0 | 0.0 |

The pre-correction run's zero emissions from 2040 are an artefact of its H2-conversion and diesel units, which carry zero emissions from 2040 (§11.1).

### 8.4 Annual system costs by carrier (bn ZAR/yr, undiscounted; `n.statistics.capex()` / `opex()`) [CONFIRMED]

Corrected run, annualised capital + fixed O&M:

| Carrier | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| solar_pv + solar_pv_low | 0.0 | 94.6 | 148.4 | 180.9 | 223.8 | 265.3 |
| coal (existing FOM, nameplate)² | 50.7 | 43.3 | 32.7 | 32.7 | 15.4 | 15.4 |
| OCGT-class (gas + H2 + diesel) | 0.9 | 27.6 | 38.8 | 49.6 | 60.8 | 74.9 |
| ccgt_steam | 0.0 | 3.4 | 6.3 | 6.6 | 6.6 | 8.8 |
| nuclear / phs / battery_4h (existing) | 2.9 / 4.1 / 0.6 | 2.9 / 4.1 / 1.4 | 2.9 / 4.1 / 1.4 | 2.9 / 4.1 / 0.8 | 2.9 / 4.1 / 0 | 0 / 4.1 / 0 |

Corrected run, variable operating cost incl. carbon tax:

| Carrier | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| coal | 138.5 | 40.5 | 0.5 | 0 | 0 | 0 |
| OCGT-class gas/H2 | 0 | 15.8 | 27.7 | 25.3 | 22.0 | 24.3 |
| wind / csp / solar | 13.8 / 6.3 / 10.0 | 13.8 / 6.3 / 10.4 | 9.6 / 6.3 / 10.3 | 4.8 / 6.3 / 3.8 | 0 / 4.5 / 1.6 | 0 / 1.0 / 0.5 |

² `n.statistics.capex()` reports FOM on the full nameplate of existing coal. The retirement FOM savings enter the objective separately via `add_coal_decom` (`prepare_and_solve_network.py:324–326`) and are **not** reflected in this table.

---

## 9. Coal retirement trajectory

### 9.1 Three mechanisms [CONFIRMED]
1. **Exogenous end of life** (`fixed_technologies.xlsx`, `build_year` 2024 + `lifetime`):
   - Arnot, Camden, Grootvlei, Hendrina and Kelvin leave before 2030; Komati is already inactive. Together ≈ 5.4 GW.
   - Duvha, Kriel and Matla are within life only in 2030.
   - Kendal, Lethabo, Matimba and Tutuka are within life to 2040.
   - Majuba, Kusile and Medupi are within life to 2050.
2. **Exogenous floor** `phased_decommissioning.xlsx::schedule::DELAYED_ESKOM_2035`. It applies as a `>=` floor from 2030. In 2030 it requires only Kriel 0.83 (≈ 2.2 GW) among stations still within life.
3. **Endogenous retirement:** `Generator-p_nom_ret` ∈ [0,1] per station and period (`prepare_and_solve_network.py:233–352`). Retiring saves FOM × weight × p_nom, and reduces the unit's status and reserve-margin credit.

### 9.2 Endogenous retirement fractions (`outputs/decom_status.csv`; fractions ≥ 10⁻³) [CONFIRMED]

| Station (MW) | Corrected 2030 | Corrected 2035 | Pre-corr. 2030 | Pre-corr. 2035 |
|---|---|---|---|---|
| Duvha (2,875) | 1.000 | — | 1.000 | — |
| Kendal (3,840) | 0.997 | 0.003 | 0.997 | 0.003 |
| Kriel (2,640) | 1.000 | — | 1.000 | — |
| Kusile (4,320) | 1.000 | — | 1.000 | — |
| Lethabo (3,558) | 0.740 | 0.260 | 0.950 | 0.050 |
| Majuba (3,807) | 0.961 | 0.039 | 0.961 | 0.039 |
| Matla (3,450) | 1.000 | — | 1.000 | — |
| Tutuka (3,510) | 1.000 | — | 1.000 | — |
| Matimba (3,690) | — | 1.000 | — | 1.000 |
| Medupi (4,320) | — | 1.000 | — | 1.000 |
| **Cumulative retired (MW)** | **26,915** | **27,045** | 27,662 | 27,045 |

- Coal output falls from 170 TWh (2025) to 41 TWh (2030) and 0.3 TWh (2035).
- Matimba and Medupi, the stations with the lowest marginal cost, run at full status through 2030 and retire in 2035.
- Recently commissioned Kusile is retired in 2030.

### 9.3 Drivers
1. **Energy value lost to block-averaged solar.** [CONFIRMED mechanism; VALIDATE magnitude]
   - With no diurnal cycle (§4), solar PV behaves like low-cost near-baseload energy: annualised cost ≈ 1,955 kZAR/MW-yr at block-mean CF ≈ 0.32, i.e. ≈ 0.70 kZAR/MWh before curtailment.
   - Coal's carbon-taxed marginal cost rises from 0.61–1.16 kZAR/MWh (2025) to 0.95–1.83 (2030) and 1.35–2.45 (2035).
   - [VALIDATE] the split between CT_2050 and fuel-price escalation.
2. **Capacity value is cheaper from OCGTs.** [CONFIRMED]
   - Retaining existing coal costs ≈ 1,184–1,275 kZAR/MW-yr FOM at a capacity credit of 0.53, i.e. ≈ 2,235–2,400 kZAR per credited MW-yr.
   - A new OCGT costs 1,751 kZAR/MW-yr at credit 1.0.
   - Keeping coal purely for the reserve margin is therefore ≈ 28–37% dearer than building OCGTs.
3. **Operational and structural factors.** [ASSUMPTION]
   - UC minimum stable level 0.65 (`override_coal_msl`) and annual availability `EAF_60` both reduce coal's value in a solar-dominated system.
   - Perfect foresight and 5-year lumpy periods (2030 is the first decision point) produce a step change rather than a gradual decline.

[VALIDATE] The ≈ 27 GW retirement in 2030 is likely to be substantially smaller at a resolution that represents nights, solar droughts and hourly peaks. This has not been tested.

---

## 10. Comparison with the pre-correction REF-LC run

> **Caveat — two changes combined.** The original run (2026-10-06) and the corrected run (2026-10-22) differ in **two** modelling changes at once:
> 1. the reserve-margin fix (retired coal is now deducted), and
> 2. the removal of the inherited 40%/30% monthly minimum-CF obligations on new gas and CCGT steam (`NO_MIN_GAS` → `NO_GAS_FLOOR`).
>
> The differences below are the joint effect. Their individual contributions cannot be separated without a run that applies one change at a time. Inputs other than these two (and `regions`, which was already 1 in both runs) are the same as far as can be established. The original run's exact workbook state was never committed (see the backup `README.md`).

| Metric | Pre-correction | Corrected | Note |
|---|---|---|---|
| Objective (kZAR, PV) | 2.5885 × 10⁹ | 2.6740 × 10⁹ | +3.3% |
| Reserve margin, net of retired coal | violated by 6.6–14.7 GW | met (binding) | §5 |
| New ocgt_gas, 2050 (GW) | 0 | 10.7 | The floor no longer penalises gas |
| New ccgt_steam, 2050 (GW) | 0 | 4.4 | idem |
| H2-conversion OCGT, 2050 (GW) | 19.8 | 25.5 | First built in 2030 instead of 2040 |
| ocgt_diesel (existing + new), 2050 (GW) | 20.1 | 6.5 | Pre-correction diesel built as zero-emission capacity post-2040 |
| OCGT-class total, 2050 (GW) | 39.9 | 42.8 | |
| Solar PV total, 2050 (GW) | 150.9 | 155.0 | |
| Wind, 2030 (GW) | 8.8 (4.6 new) | 4.3 (no new) | |
| Coal retired, cumulative 2030 (MW) | 27,662 | 26,915 | Similar; Lethabo phasing differs |
| Coal generation 2030 (TWh) | 34.7 | 41.0 | |
| CO₂ 2030 / 2050 (Mt) | 41.9 / 0.0 | 51.5 / 4.2 | Corrected run dispatches natural gas in 2045–50 |
| Mean price 2030 / 2050 (kZAR/MWh) | 1.036 / 0.716 | 0.952 / 0.685 | Time-weighted mean of the bus marginal price |
| sasol_gas CF 2030 | 19% | 0% | [VALIDATE] |
| Load shedding | ≈ 0 | ≈ 0 | |

**Interpretation** [ASSUMPTION]:
- The pre-correction run was infeasible with respect to the intended reserve-margin policy. It is therefore not a valid least-cost reference.
- Its absence of natural-gas investment reflected the take-or-pay floors and the uncredited retired coal, not an economic verdict on gas.

---

## 11. Technology representation findings

### 11.1 OCGT technology options and hydrogen conversion

Assumptions for new OCGT-class options under the REF-LC labels:

| Carrier | Capex (R/kW) | FOM (R/kW-yr) | VOM (R/MWh) | η | Life (yr) | Fuel 2025/30/35 (R/GJ) | Fuel 2040/45/50 (R/GJ) | Emissions 2025–35 → 2040+ (kgCO₂/GJ) | RM credit |
|---|---|---|---|---|---|---|---|---|---|
| ocgt_gas | 15,715 | 64.7 | 82.7 | 0.381 | 30 | 216 / 211 / 217 | 223 / 227 / 239 | 69 → 69 | 1.0 |
| ocgt_diesel (new) | 15,715 | 64.7 | 82.7 | 0.381 | 30 | 389 / 382 / 391 | 399 / 406 / 424 | 74 → **0** | 1.0 |
| ocgt_gas_h2_40 | same | same | same | same | same | = gas | **= diesel** 2040–50 | 69 → **0** from 2040 | 1.0 |
| ocgt_gas_h2_45 | same | same | same | same | same | = gas | gas, then **= diesel** from 2045 | **0** from 2045 | 1.0 |
| ocgt_gas_h2_50 | same | same | same | same | same | = gas | gas, then **= diesel** 2050 | **0** in 2050 | 1.0 |
| ocgt_gas_h2_55 / _60 | same | same | same | same | same | = gas | = gas | 69 | **absent → 0** |
| ccgt_steam | 17,831 | 43.1 | 17.0 | 1.0 | 30 | 0 | 0 | 0 | 1.0 |

Sources (`scenarios/Coal_Flexibilisation/sub_scenarios/`):
- `extendable_technologies.xlsx::parameter_mapping/parameters::BASE_PMR1b` (total-vs-overnight ratio `WACC_0923`; FOM, VOM, η and lifetime from "default" rows);
- `fuel_prices.xlsx::extendable_generators::BASE_PMR1b`;
- `emissions.xlsx::extendable_generator_emissions::BASE`;
- `reserve_margin.xlsx::capacity_credits::BASE2`.

Marginal cost = 3.6 × fuel / η + VOM + emissions × carbon tax (`add_electricity.py:1124–1180`).

**Findings**
- **[CONFIRMED] `ocgt_gas_h2_YY` denotes an OCGT that switches to hydrogen in year YY, not a blend share.**
  - At conversion its fuel price becomes exactly the diesel price and its emissions drop to zero.
  - There is no hydrogen-readiness capex premium, no conversion capex, and no hydrogen supply constraint.
  - The code has no hydrogen logic; these are purely data-defined carriers.
- **[VALIDATE]** Whether the hydrogen price is a placeholder copied from the diesel row, and whether zero emissions for new `ocgt_diesel` from 2040 are intended (e.g. renewable diesel) or a data error.
- **[CONFIRMED] Degeneracy.**
  - All seven OCGT carriers share identical capex, FOM, VOM, efficiency and lifetime.
  - Capacity bought only for the reserve margin and never dispatched is therefore *exactly* tied across `ocgt_gas`, new `ocgt_diesel` and `h2_40/45/50`.
  - A 2050 vintage is also tied on energy cost for `ocgt_diesel` and `h2_40/45/50`: all four use the diesel price with zero emissions.
  - The barrier solver without crossover returns the centre of the optimal face, which spreads capacity evenly across tied options. The 2050 vintage is **exactly 1,611.80 MW** each for `ocgt_diesel`, `h2_40`, `h2_45` and `h2_50`, and the 2030 vintage is split 2,808 / 2,837 / 2,841 / 2,865 MW. This is the characteristic signature.
  - `h2_55/60` are dominated (no capacity credit) and never built.
- **Consequence:** the allocation of OCGT-class capacity between "natural gas", "hydrogen-ready" and "diesel" in REF-LC is **arbitrary**. Only aggregate OCGT-class capacity is a meaningful least-cost result.

**Implications for mandated gas and stranded assets** [ASSUMPTION / VALIDATE]:
- POL mandates force `ocgt_gas` (2,100 MW) and `ccgt_steam` (900 MW) in 2030 (`extendable_technologies.xlsx::min_annual_installed::3GW_GAS`; `6GW_GAS` currently holds the same values, which is an open data issue).
- REF-LC already has 18.4 GW of OCGT-class capacity active in 2030, so a mandate of this size mostly **relabels** tied H2/diesel units as natural gas at almost no system cost.
- The proposed stranding metric ("mandated MW that least-cost would not build") would then be close to zero by construction.
- In addition, free conversion of H2-ready units removes any stranding risk for them after the conversion year by assumption.

### 11.2 CCGT steam representation
- **[CONFIRMED] Coupling.** `custom_constraints.ccgt_steam_constraints` (`custom_constraints.py:189–227`) imposes, per bus, period and snapshot:
  Σ p(ccgt_steam) ≤ 0.427 × Σ p(feeding units).
  - The feeding units are every carrier listed in `aux_stg_feed.xlsx::allowable_carriers::DIESEL_LNG`: `ocgt_gas`, `ocgt_diesel` (including the existing Ankerlig, Gourikwa, Avon, Dedisa, Acacia and Port Rex units) and all `ocgt_gas_h2_*`.
  - The coupling links **energy only**. Steam capacity is not tied to any gas-turbine capacity or vintage.
  - The `bus == bus` query makes the constraint system-wide (harmless at 1 node).
  - Ex post, the constraint holds in every snapshot and binds in 11–22 of 48 blocks per period.
- **[CONFIRMED] Reserve-margin credit.** `ccgt_steam` receives credit 1.0 regardless of the gas-turbine capacity able to feed it.
  - In REF-LC, steam capacity is 9–13% of the feeding OCGT-class fleet, below the 0.427 ratio. There is therefore no numerical double counting in this run.
  - The treatment is still structurally permissive:
    - open-cycle peakers, diesel units and hydrogen-converted units can "feed" a steam turbine without a heat-recovery steam generator;
    - the credit would overstate firm capacity in any scenario where steam capacity exceeds 0.427 × paired gas-turbine capacity.
- **[VALIDATE]** Installed steam capacity (4.4 GW in 2050) exceeds its maximum dispatched output (≤ 2.5 GW). Check its `p_max_pu`, and whether this is interior-point spreading.
- **Candidate representations** (not implemented, for agreement):
  - **B1 (recommended for development):** one aggregated `ccgt_gas` generator.
    - Blended capex ≈ (GT + 0.427 × ST) / 1.427 per kW.
    - Efficiency ≈ 0.381 × 1.427 ≈ 0.54.
    - Gas fuel and emissions, with its own capacity credit.
    - This removes the coupling ambiguity and the RM credit issue.
  - **B2:** keep the split representation, with three additions:
    - a dedicated `ccgt_gt` carrier as the only steam feed;
    - a capacity constraint p_nom(steam) ≤ 0.427 × p_nom(ccgt_gt) per vintage;
    - an RM credit for steam limited to 0.427 × credited `ccgt_gt`.
    - Requires code changes.

### 11.3 Technology scope options for the gas-policy framework (pending agreement)

| Option | Description | Advantages | Disadvantages / research implications |
|---|---|---|---|
| **C1. Gas-study development set** (recommended for POL development runs) | New `extendable_active` label: `ocgt_gas` + CCGT (B1 or B2); `ocgt_gas_h2_*` and new `ocgt_diesel` disabled; existing diesel fleet retained | Removes degeneracy; natural-gas build and mandated excess are identifiable; stranding metrics measurable against REF | Removes the hydrogen-ready hedge. The remaining firm alternatives are batteries, PHS, coal and nuclear, so gas need may be overstated. Must be documented as a scope choice |
| **C2. Differentiated alternatives** (later sensitivity, e.g. on POL-6GW) | Keep one H2-ready OCGT and new diesel, with sourced data: H2-ready capex premium, conversion capex, H2 price path, correct diesel emissions; consider Crossover on for vertex solutions | Directly addresses "gas versus H2-ready as a stranding hedge" | Requires new data; residual near-ties possible; results sensitive to H2 assumptions; more workbook labels |
| C3. Status quo with aggregate reporting | No input changes; report OCGT-class aggregates only | No edits required | Natural-gas builds cannot be attributed; mandates ≈ relabelling; the stranded-asset question cannot be answered |

---

## 12. Limitations and open questions

| # | Item | Tag | Effect on interpretation |
|---|---|---|---|
| L1 | **LC-182h block averaging removes the diurnal cycle.** Solar never falls below 0.22 pu; load is a 182-h mean. | [CONFIRMED] | Dominates coal retirement, solar share, the absence of storage, and peaker utilisation. Capacity factors, utilisation and revenue-based stranding metrics from LC-182h runs are not reportable findings. |
| L2 | Reserve-margin peak is the block-mean peak, not the hourly peak. | [CONFIRMED] mechanism / [VALIDATE] magnitude | Firm requirement likely understated. |
| L3 | OCGT-class technology degeneracy and interior-point spreading (§11.1). | [CONFIRMED] | Carrier split is arbitrary; mandate costs and stranding are biased towards zero. |
| L4 | Hydrogen conversion: free, at the diesel price, zero emissions; new diesel zero-emission from 2040. | [CONFIRMED] data / [VALIDATE] intent | Distorts post-2040 emissions and the value of H2-ready capacity. |
| L5 | CCGT steam is coupled by energy only; RM credit is independent of the paired GT (§11.2). | [CONFIRMED] | No double count in REF-LC; risk in CCGT-mandate scenarios. |
| L6 | Coal capacity credit 0.53 vs 1.0 for OCGT/steam; EAF_60; MSL 0.65. | [ASSUMPTION] | Favours replacing coal capacity with OCGTs. |
| L7 | Final period weighted 50 years. | [CONFIRMED] | Terminal bias on 2050 conditions and late builds. |
| L8 | No early-retirement option for new gas. | [CONFIRMED] | Stranding must be measured ex post. |
| L9 | Termination OPTIMAL recovered, but the final gap/bound was not preserved; no solver log is written by default. | [CONFIRMED] | Future runs should keep the full Gurobi log. |
| L10 | Retirement objective constant enters with a sign that appears inverted. | [CONFIRMED] code / [VALIDATE] | Absolute objective is offset by a constant; comparisons are unaffected. |
| L11 | `n.statistics` capex includes FOM of retired coal at nameplate. | [CONFIRMED] | Cost tables overstate coal fixed costs after retirement. |
| L12 | Existing wind retires with no new wind built; nuclear (Koeberg) leaves by 2050; sasol_gas CF falls to 0. | [CONFIRMED] output / [VALIDATE] plausibility | Likely consequences of L1 and of the input data. |
| L13 | Carbon-tax versus fuel-price contribution to coal marginal cost growth. | [VALIDATE] | Attribution of the coal exit. |
| L14 | Duals of custom constraints (reserve margin, retirement) are not saved in `solved.nc`. | [CONFIRMED] | The capacity value of gas cannot be read directly. |
| L15 | Separation of the RM-fix and gas-floor effects (§10). | [VALIDATE] | Needs a one-change-at-a-time run if attribution is required. |
| L16 | Open data issues from the audit: `6GW_GAS` duplicates `3GW_GAS`; `min_total_installed` header; missing gas price / contract labels. | [CONFIRMED] | Must be fixed before the corresponding POL scenarios. |

---

## 13. Recommendations

**Accept** the corrected REF-LC run as the development least-cost reference at 1 node and LC-182h. It is optimal, feasible, compliant with the reserve margin net of retired coal, and free of load shedding.

**Resolve before running POL-3GW, POL-6GW and POL-16GW:**
1. **OCGT degeneracy and hydrogen-conversion assumptions (L3, L4).** Agree a technology scope (recommended: option C1 for development runs, with C2 as a later sensitivity). Confirm the intended hydrogen and diesel price/emission data. Without this, mandated-gas costs and stranding are not identifiable.
2. **CCGT representation (L5).** Agree B1 or B2, since CCGT is part of every gas mandate.
3. **Metric scope at LC-182h (L1).** Agree that development runs report capacity, reserve-margin-driven investment and cost differences. Capacity factors, utilisation and revenue-based stranding metrics are not to be reported as findings.
4. **Scenario data defects affecting POL rows (L16).** These include distinct `6GW_GAS` values and the other open audit items listed in the checklist.
5. **Solver logging (L9).** Arrange for the full Gurobi log to be retained for each run, e.g. a `LogFile` solver option or a Snakemake `log:` directive (requires approval to edit configuration or `Snakefile`).

**Document as limitations of the development model:** L2, L6, L7, L8, L10–L15. In particular:
- the magnitude and timing of coal retirement, which should be treated as a sensitivity on the POL-6GW anchor;
- the block-mean reserve-margin peak;
- the 50-year terminal weight;
- the combined-change caveat on the pre-correction comparison.

---

## Appendix A — Traceable sources

**Model code**
- `scripts/prepare_and_solve_network.py`:
  - `add_coal_decom` (233–352);
  - `solve_network` (461–490), which calls `set_operational_limits` (465), `ccgt_steam_constraints` (466), `add_coal_decom` (471) and `reserve_margin_constraints` (478), then `solve_model` (490);
  - `scale_costs` (493, called at 561);
  - Threads override (545).
- `scripts/custom_constraints.py`:
  - `ccgt_steam_constraints` (189–227);
  - `reserve_margin_constraints` (256–325), with the correction at 324.
- `scripts/add_electricity.py`:
  - `load_extendable_parameters` (271);
  - `apply_variable_fuel_costs_for_extendable_generators` (1124);
  - `apply_emissions_for_extendable_generators` (1147).
- `scripts/base_network.py:124`: final-period weighting.
- `config.yaml`:
  - `solver.gurobi`;
  - `electricity.conventional_generators.ccgt_st_to_gt_ratio` (95);
  - `endogenous_decomssioning_start_year` (91);
  - `costs` (193–194).

**Workbooks** (`scenarios/Coal_Flexibilisation/`)
- `scenarios_to_run.xlsx::scenario_definition` (REF-LC row)
- `sub_scenarios/operational_constraints.xlsx::operational_constraints` (`NO_MIN_GAS`, `NO_GAS_FLOOR`)
- `sub_scenarios/extendable_technologies.xlsx` (`active::BASE`, `parameter_mapping`/`parameters::BASE_PMR1b`, `min_annual_installed`)
- `sub_scenarios/fuel_prices.xlsx::extendable_generators::BASE_PMR1b`
- `sub_scenarios/emissions.xlsx` (`carbon_tax::CT_2050`, `extendable_generator_emissions::BASE`)
- `sub_scenarios/reserve_margin.xlsx` (`reserve_margin::RES_MRGN_10`, `capacity_credits::BASE2`)
- `sub_scenarios/phased_decommissioning.xlsx::schedule::DELAYED_ESKOM_2035`
- `sub_scenarios/aux_stg_feed.xlsx::allowable_carriers::DIESEL_LNG`

**Outputs (corrected run)**
- `results/Coal_Flexibilisation/REF-LC/LC-182h/networks/solved.nc`
- `results/Coal_Flexibilisation/REF-LC/LC-182h/outputs/`: `decom_status.csv`, `generators.csv`, `generator_emissions.csv`, `network_stats.csv`, `storage_units.csv`, `capacity_value.csv`, `full_outages.csv`, `plots/`
- `networks/Coal_Flexibilisation/REF-LC/LC-182h/elec.nc` (solve input), `base-network.nc`
- `.snakemake/log/2026-10-22T191716.579753.snakemake.log`

**Pre-correction reference**
- `backups/REF-LC_LC-182h_pre-correction_2026-10-22/` (README, `MANIFEST.sha256`, provenance log `2026-10-06T150519.053730.snakemake.log`). Excluded from git via `.git/info/exclude`.

**Method**
- All figures were computed read-only from the files above with PyPSA 0.35.2 in the `pypsa-rsa` environment.
- No model was re-run for this report.
