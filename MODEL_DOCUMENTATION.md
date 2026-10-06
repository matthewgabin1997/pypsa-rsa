# Model Documentation: PyPSA-RSA Carbon Tax Analysis

Last updated: 2026-09-15

This document describes the current state of the PyPSA-RSA carbon-tax model: what it does, why the parameters are set the way they are, what's been fixed vs. still open, and how to actually run it. All parameter values below were verified directly against the live `scenarios_to_run.xlsx` on 2026-09-15

**Model framework:** [PyPSA](https://pypsa.org/) (Python for Power System Analysis)
**Base repository:** Fork of [Meridian Economics PyPSA-RSA](https://github.com/MeridianEconomics/pypsa-rsa)
**Working directory:** `/beegfs/scratch/agma/pypsa-rsa`
**Scenario folder:** `scenarios/Coal_Flexibilisation/` (sub-scenarios in `scenarios/Coal_Flexibilisation/sub_scenarios/`)

---

## 1. Research Questions

- **RQ1:** What are carbon tax revenues under an IRP-aligned 2030 baseline, and are they sufficient to drive significant RE expansion?
- **RQ2:** Does the CT price signal change the cost-optimal 2030 capacity mix?
- **RQ3:** Does reinvesting CT revenues into renewables accelerate the transition — and does it matter whether the price signal existed beforehand?

**Headline CT rate: 462 R/tCO₂ in 2030** (SA National Treasury rate, 2022 Taxation Laws Amendment Act, IRP23-aligned trajectory). This is the *headline* rate, not the effective rate after tax-free allowances (~60% currently, ~185 R/t effective) — used deliberately as an upper-bound / maximum-policy-impact scenario, stated as a methodological choice in the paper.

---

## 2. Scenario Design

### P0 — 2030 snapshot (Paper 0, current focus)

2×2 matrix isolating the CT price signal from revenue recycling:

| Scenario            | CT in optimisation? | Revenue recycling? | Description                          |
| ------------------- | ------------------- | ------------------ | ------------------------------------ |
| **P0_BASE**   | No                  | No                 | IRP baseline — no CT, no recycling  |
| **P0_BASE_R** | No                  | Yes                | Baseline + mandatory RE reinvestment |
| **P0_CT**     | Yes (462 R/tCO₂)   | No                 | CT as pure price signal              |
| **P0_CT_R**   | Yes (462 R/tCO₂)   | Yes                | CT + mandatory RE reinvestment       |

Three core comparisons: BASE vs CT (price-signal effect) · BASE vs BASE_R (recycling effect alone) · CT vs CT_R (recycling on top of an existing price signal).

`simulation_years = 2025, 2030`: two investment periods. 2025 anchors the existing fleet (fixed capacity); 2030 is the policy year where all investment/dispatch is optimised and all results are reported. `run_scenario = true` for all four P0 rows — these are the active scenarios.

### P1 — pathway (2025–2050, for a separate IEW paper)

P1_BASE, P1_BASE_R, P1_CT, P1_CT_R use the same 2×2 logic but `simulation_years = 2025, 2030, 2035, 2040, 2045, 2050` (six periods) and `regions = 1` (single-node, no transmission). **Currently inactive** (`run_scenario = False` for all four P1 rows in the live xlsx) — not part of the current run queue.

---

## 3. What Changed and Why (condensed changelog)

- **2026-09-13 — Enabled endogenous coal retirement** (`unit_committment: 0→1`, `endogenous_coal_decom: 0→1`, P0 only). Motivation: with these off, CT can change *how much* coal dispatches but never *when* it retires — doesn't let the model test whether CT accelerates retirement, a core Paper 0 question. `endogenous_coal_decom` is only read inside `add_coal_decom()` (`prepare_and_solve_network.py`), itself only called when `unit_committment=1` — both flags must be set together or the retirement variable (`Generator-p_nom_ret`) doesn't exist. With both on, the retirement constraint becomes a floor (`p_nom_ret >= phased_decom_schedule`) instead of an exact match — the model can retire earlier if uneconomic.
  `dispatch_coal_flex` stays at `SL_0` (no intra-year cycling — deliberately) even with UC on: MSL already applies unconditionally via `set_coal_msl()` regardless of UC, so coal can already track the CT price signal between its MSL floor and `p_max_pu` every hour. `SL_0` withholds only the ability to shut a block fully off and restart — keeping it off isolates the CT-retirement effect from a second free variable (cycling behaviour) and is the stricter test (upper bound on the CT retirement effect; enabling cycling would tend to reduce it).
- **2026-09-13 — `override_coal_msl` raised 0.4 → 0.65.** 0.4 was too low relative to the fleet's own data: the per-station `min_stable_level (%)` column in `fixed_technologies.xlsx::conventional` lists 0.65 for every fixed coal/sasol_coal unit, so 0.65 reflects the plants' documented minimum stable level rather than an arbitrary override value. Checked whether that per-station column could be read directly instead of a blanket override: all 17 fixed coal/sasol_coal units already carry the identical value 0.65 (no real per-station differentiation to recover), **and** the column is dead code for fixed generators anyway — `attach_fixed_generators()` zeroes `p_min_pu` for every generator and only ever overwrites it for wind/solar/RMIPPP, never coal, then commits that 0 as a time-varying override that always wins over the static per-station value (`add_electricity.py:439-440,1043`). There's an unused function `adjust_com_msl()` (`add_electricity.py:1442`) that would restore the static value but is never called. Net effect: setting `override_coal_msl=0.65` directly reproduces what a working per-station read would give — no code change needed. Wiring up `adjust_com_msl()` is only worth doing if the per-station values are later differentiated by plant/technology.
- **Coal ramp rate multiplier reverted 1.5× → 1× for P0** (still 1.5× for P1). The 1.5× "Coal Flexibilisation" assumption was reverted for the same reason as `dispatch_coal_flex=SL_0` above — avoid a second free flexibility variable confounding the CT-retirement signal being tested in P0. Also has limited effect at `LC-182h` (non-consecutive timesteps), more relevant once full `LC` (8760h, consecutive) is used.
- **`fixed_conventional`: VAR_HR → BASE_PMR1b.** Design-efficiency heat rates (VAR_HR) suppressed the CT signal entirely — coal remained cheaper than gas even with full CT applied. BASE_PMR1b uses realistic current Eskom heat rates (e.g. Medupi 9.58 GJ/MWh, ~38% efficiency).
- **`extendable_min_total`: history UNC → (briefly) IRP25_BQ in an intermediate doc draft → back to UNC (current, confirmed live).** Original rationale for UNC (still valid, still the live setting): an IRP-mandated minimum RE build (`IRP25_BQ`) would crowd out the CT signal — both BASE and CT would end up building similar RE volumes regardless of carbon price, because the *mandate* rather than the *price signal* drives buildout. With `UNC`, BASE builds only what's cost-optimal without a carbon price (lower RE, higher coal dispatch) and CT invests in RE because coal dispatch has become expensive — so the BASE vs CT difference is a clean measure of the CT effect on investment, not conflated with a policy mandate. Caveat: UNC is a theoretical counterfactual (in practice some IRP2025 projects are already contracted) and should be stated as such in the paper.
- **`extendable_max_annual`: UNC for all four P0 scenarios (not just `_R`).** Originally `_R` scenarios needed UNC as a technical necessity — under `MOD_CNST`, wind is capped at ~1 GW/yr, but a ~70 bn ZAR CT-reinvestment floor needs ~5.8 GW of new wind, making the constraint infeasible under `MOD_CNST`. This was then generalised to all four P0 scenarios so the *only* differences between them are the CT price signal and the reinvestment constraint, not differing build-rate caps.
- **regions: 1 → 10 for P0** (multi-node, 10 Eskom supply regions + real transmission network). Two multi-node bugs found and fixed along the way (both resolved, kept for reference): (1) `build_topology.py` read a stale column name `capacity_expansion_years` instead of `simulation_years`; (2) a SIGSEGV in `add_electricity.py`'s renewable-profile loading loop (lines 624–632) was caused by converting an xarray DataArray to pandas before a per-bus `.sel()` loop — fixed by keeping it as xarray and selecting per-bus inside the loop.
- **Transmission: fixed → extendable on existing corridors** (`line_expansion=copt`). Originally the network had `p_nom_extendable=False` everywhere (sunk-cost assumption, no grid capex in the objective). Now existing corridors can be expanded by the optimizer at a real cost (see §7). New corridors (not on the existing grid) are still not modelled — see §8.
- **`carbon_tax` / `carbon_constraints` labels:** the CT trajectory used to be called `IRP23` in an early doc draft; the live `emissions.xlsx::carbon_tax` sheet names it `CT_2030` (single non-zero value: 0 everywhere except 462 R/t in 2030) — same numbers, just a different sheet-row name. P1 uses `CT_2050`, a full ramp (190 R/t in 2024 → 462 in 2030 → escalating to 2189 R/t in 2050, ~86.3 R/t/yr from 2031).
- **`capacity_credits`: BASE3 (doc draft) never matched live data → BASE2 is and has been the live setting.** BASE2: coal 53%, nuclear/OCGT/CCGT/PHS/biomass 100%, battery 4h 50%, battery 8h 75%, solar CSP 50%, wind/wind_low 10%, solar PV (all) 0%. See §4 for the full table.
- **`load_trajectory`: IRP24_LOW (doc draft) never matched live data →** P0 actually uses `LOWDelEVs`, P1 uses `IRP24_MOD`. `[VERIFY: exact demand-growth assumptions behind LOWDelEVs vs IRP24_LOW — likely a renamed/updated trajectory in annual_load.xlsx, not independently re-derived here]`.
- **Excel boolean truthiness gotcha (still relevant, not a bug fix so much as an operating rule):** `_helpers.py` fills empty scenario-setup cells with the string `"none"`, which is truthy. `add_electricity.py` checks these fields with `== True` (safe against empty cells) but `prepare_and_solve_network.py` and `custom_constraints.py` use plain `if ...:` truthy checks for `unit_committment` / `endogenous_coal_decom` / `variable_storage_vom` — an accidentally-blank cell there is silently treated as "on" and can raise `KeyError: 'Generator-status'`. **Rule: always fill these three cells explicitly with `0`, never leave blank.** (Not yet fixed at the code level — `== True`/`== 1` checks would need to replace the truthy checks in those two files to make blank cells safe.)
- **Cost-scaling export bug — root cause found, not yet fixed.** `scale_costs(n, 1e3)` (`prepare_and_solve_network.py:561`) divides all `capital_cost`/`marginal_cost` columns by 1000 before the solve (for solver numerical conditioning) and is **never called again to scale back up** before `export_to_netcdf()`. So every `solved.nc` has `capital_cost`, `marginal_cost`, and derived duals (`marginal_price` etc.) in **thousand-ZAR, not ZAR**. This was originally mistaken for a real transmission-expansion mystery (why doesn't the optimizer expand a 99.999%-loaded corridor?) — it doesn't, and that's economically correct: reconstructing the true (×1000) numbers, the Free State–Gauteng corridor's congestion rent (~144,000 ZAR/MW/yr average) sits well below its expansion cost (~291,000 ZAR/MW/yr) — no bug, no missed opportunity, just a misleading raw export. **Fix (not yet applied):** call `scale_costs(n, 1e-3)` again right before `export_to_netcdf()`, or at minimum document "costs in solved.nc are in thousand-ZAR" wherever they're consumed.

---

## 4. Current Parameter State — P0 (live, verified 2026-09-15)

All four P0 scenarios (`P0_BASE`, `P0_BASE_R`, `P0_CT`, `P0_CT_R`) share every column below **except** `carbon_tax` and `carbon_constraints`.

### 4.1 Solver & run control

| Parameter        | Value                                                                    |
| ---------------- | ------------------------------------------------------------------------ |
| `solver`       | `gurobi`                                                               |
| `run_scenario` | `true` (all four P0 rows active; all four P1 rows currently `False`) |

### 4.2 Time & weather

| Parameter            | Value                                                      | Notes                                                                                                                                                  |
| -------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `simulation_years` | `2025, 2030`                                             | 2025 anchors existing fleet, 2030 is the reported/optimised year                                                                                       |
| `options`          | **`LC-2190h`** (as of 2026-09-15, active test run) | Production default is`LC` (full 8760h, no averaging). See §9 for what `LC-Nh` actually does — it's a block-mean average, not TSAM day-selection. |
| `weather`          | `W_P50`                                                  | Median weather year, mapped to historical 2018                                                                                                         |

### 4.3 Network & spatial resolution

| Parameter             | Value                                                                              |
| --------------------- | ---------------------------------------------------------------------------------- |
| `regions`           | `10` (P0) / `1` (P1)                                                           |
| `resource_area`     | `redz_corridors_eia` — broadest renewable candidate site set                    |
| `transmission_grid` | `existing+tdp` — existing 400kV grid + Eskom TDP 2023 planned lines             |
| `line_expansion`    | `copt` — endogenous expansion enabled on existing corridors (optimizer decides) |

### 4.4 Coal fleet

| Parameter                     | Value                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `fixed_conventional`        | `BASE_PMR1b`                                                                    |
| `phased_decom`              | `DELAYED_ESKOM_2035` (floor schedule; retirement can happen earlier — see §3) |
| `override_coal_msl`         | `0.65`                                                                          |
| `coal_ramp_rate_multiplier` | `1` (P0) / `1.5` (P1)                                                         |
| `annual_availability`       | `EAF_60` (60% EAF)                                                              |
| `unit_committment`          | `1` (P0) / `0` (P1)                                                           |
| `endogenous_coal_decom`     | `1` (P0) / `0` (P1)                                                           |
| `dispatch_coal_flex`        | `SL_0` (no intra-year cycling)                                                  |

### 4.5 Costs & investment

| Parameter                                          | Value                                                                                                          |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `extendable_parameters`                          | `BASE_PMR1b` — Wind 24,739 / Solar 15,690 / OCGT 15,715 / Battery 4h 13,581 ZAR/kWel (2030 overnight capex) |
| `extendable_fuel_prices` / `fixed_fuel_prices` | `BASE_PMR1b` — coal 40.0→58.9 R/GJ (2025→2030)                                                            |
| `global_discount_rate`                           | `0.092` (9.2%)                                                                                               |
| `extendable_active`                              | `BASE`                                                                                                       |
| `variable_storage_vom`                           | `1`                                                                                                          |

### 4.6 Emissions

| Parameter                                      | Value                                             |
| ---------------------------------------------- | ------------------------------------------------- |
| `fixed_emissions` / `extendable_emissions` | `BASE` (no fuel-switching / no H₂ assumptions) |

### 4.7 Build constraints

| Parameter                 | Value   | Rationale                                                        |
| ------------------------- | ------- | ---------------------------------------------------------------- |
| `extendable_min_total`  | `UNC` | No IRP pipeline floor — investment is fully endogenous, see §3 |
| `extendable_max_total`  | `UNC` | No upper cap                                                     |
| `extendable_max_annual` | `UNC` | No annual build-rate cap, any scenario — see §3                |
| `extendable_min_annual` | `UNC` | No annual minimum                                                |

### 4.8 Fixed existing assets

| Parameter                                | Value    |
| ---------------------------------------- | -------- |
| `fixed_renewables` / `fixed_storage` | `BASE` |

### 4.9 Operational constraints

| Parameter                | Value                                                                                                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `operational_limits`   | `NO_MIN_GAS` (gas dispatches only when economic)                                                                                                                                                      |
| `operational_reserves` | `BASE` — **dead in current code**, `set_operating_reserves()` call is commented out (`prepare_and_solve_network.py:467`); the sheet for this label only still exists in an archived folder |
| `outage_profiles`      | `BASE`                                                                                                                                                                                                |
| `aux_stg_feed`         | `DIESEL_LNG`                                                                                                                                                                                          |

### 4.10 Reserve margin & capacity credits

| Parameter            | Value                                                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reserve_margin`   | `RES_MRGN_10` — 10% above peak, active from 2030                                                                                                                             |
| `capacity_credits` | `BASE2`: coal 53% · nuclear/OCGT/CCGT/PHS/biomass 100% · battery 4h 50%, battery 8h 75%, battery 1h 25% · solar CSP 50% · wind/wind_low 10% · solar PV (all variants) 0% |

### 4.11 Demand

| Parameter           | Value                                   |
| ------------------- | --------------------------------------- |
| `load_trajectory` | `LOWDelEVs` (P0) / `IRP24_MOD` (P1) |

### 4.12 Carbon tax & revenue recycling

| Parameter              | BASE     | BASE_R          | CT          | CT_R            |
| ---------------------- | -------- | --------------- | ----------- | --------------- |
| `carbon_tax`         | `none` | `none`        | `CT_2030` | `CT_2030`     |
| `carbon_constraints` | `none` | `CT_REINVEST` | `none`    | `CT_REINVEST` |

`CT_2030` trajectory (`emissions.xlsx::carbon_tax`): 0 R/t every year except **462 R/t in 2030**. `CT_2050` (P1 only): 190 (2024) → 462 (2030) → 894 (2035) → 1326 (2040) → 1757 (2045) → 2189 (2050) R/tCO₂.

---

## 5. Carbon Tax & Revenue Recycling — Mechanism

**Price signal:** `marginal_cost += carbon_tax [R/tCO₂] × emission_factor [tCO₂/MWh]` per generator.

**Revenue recycling (`_R` scenarios):** a two-stage design, deliberately not fully endogenous (endogenous would create an emissions→revenue→investment→dispatch→emissions feedback loop that makes BASE_R vs BASE harder to interpret causally):

1. Solve the reference scenario (P0_BASE for BASE_R, P0_CT for CT_R) first → extract its 2030 emissions.
2. Solve the `_R` scenario with a linopy constraint using that fixed reference-scenario revenue as RHS:
   `Σ(p_nom_new[carrier] × capital_cost) ≥ base_RE_investment + CT_revenues`, for `wind`, `wind_low`, `solar_pv`, `solar_pv_low`, `build_year == 2030` only. `base_RE_investment` (from the *reference* scenario) ensures `_R` invests *on top of* the baseline, not merely matches it. `CT_revenues = 462 R/tCO₂ × reference-scenario 2030 emissions`.

The Snakefile enforces this dependency via a lambda input: `P0_BASE_R` waits for `P0_BASE/networks/solved.nc`, `P0_CT_R` waits for `P0_CT/networks/solved.nc`.

**P1 multi-year variant** (`add_ct_reinvestment_constraint_multiyear()`) loops over all 6 investment periods instead, reinvestment pool additionally includes batteries (not PHS — resource-constrained, decade-long lead times, not a realistic near-term target), `REINVEST_FRACTION = 0.5` (50% reinvested, 50% assumed other government spending). Selected automatically: `len(n.investment_periods) <= 2` → P0 function, else → P1 function (`prepare_and_solve_network.py`).

**Observed (from the last completed P0 solve, 10-node LC-182h, pre-MSL-raise — see §10):** the reinvestment constraint is always binding — the optimizer invests exactly the floor, never more (known limitation, see §7).

---

## 6. Network & Temporal Resolution

- **Nodes (P0):** 10 Eskom supply regions (Eastern Cape, Free State, Gauteng, Hydra Central, KwaZulu-Natal, Limpopo, Mpumalanga, North West, Northern Cape, Western Cape), connected by 38 bidirectional links built from shapefiles (`build_topology.py`).
- **Transmission:** existing 400kV lines (St. Clair N-1 derated capacity) + TDP planned lines. Existing corridors are extendable (`line_expansion=copt`); no new (non-existing) corridors are modelled — see §8.
- **Dispatch resolution (`options`):** currently `LC-2190h` for an in-progress smoke test; production default is `LC` (full 8760h, no averaging).

**What `LC-Nh` actually does (important — earlier docs described this wrong):** the code parses `options` on `-` and matches `^\d+h$` against `average_every_nhours()` (`add_electricity.py:1565`, regex match at line 1770) — this is a plain **pandas `resample(offset).mean()` block-average over the whole year**, not a TSAM representative-day/hour selection. `LC-182h` → ~48 blocks/investment period (182h each, averaged). `LC-2190h` → **~4 blocks/period** (quarter-year averages) — coarse enough to erase essentially all daily solar/demand variability, i.e. useful only as a pipeline/constraint smoke test, not for reading dispatch numbers. True TSAM clustering exists in the code (`^\d+SEG$` suffix, e.g. `10SEG`) but is not what any current scenario row uses.

---

## 7. Known Limitations / Open Issues

- **P1 has no mandatory coal retirement after 2035** (`phased_decom=DELAYED_ESKOM_2035`, fixed/exogenous, `endogenous_coal_decom=0`): residual coal persists indefinitely past 2035 in all P1 scenarios unless dispatch economics make it uncompetitive. Emissions stay 80–102 MtCO₂/yr in 2045–2050 even at 84–90% RE share in P1_BASE.
- **P1 is single-node (`regions=1`):** no transmission bottlenecks, so RE always reaches demand and coal competes purely on marginal cost — dilutes the CT dispatch (merit-order) channel relative to a 10-bus model. P1_CT and P1_BASE show near-identical emissions in the last full P1 run; investment/recycling channels dominate. A 10-bus P1 run is needed to capture the spatial dispatch signal properly.
- **PHS extendability is uncapped:** new PHS (`RSA-phs-{year}`) builds 1.7–3.0 GW even without recycling in the last P1 run, despite SA's PHS resource being limited (few suitable sites, 10+ year lead times). Should be capped (`extendable_max_total`) or made non-extendable. Excluded from the CT reinvestment pool already.
- **The `_R` reinvestment constraint is always binding:** the optimizer never invests beyond the floor — so `_R` scenarios are "cost-optimal subject to a forced minimum spend," not "cost-optimal with a reinvestment budget." A true budget-cap (rather than floor) formulation would be needed to test the latter.
- **Cost-scaling export bug** (§3): `solved.nc` cost/price fields are in thousand-ZAR, not ZAR, until the missing rescale-back is added before export. Doesn't affect solve correctness, only how exported numbers must be interpreted (×1000).
- **Excel boolean truthiness gotcha** (§3): always fill `unit_committment` / `endogenous_coal_decom` / `variable_storage_vom` explicitly with `0` — never leave blank.
- **`operational_reserves=BASE` is dead code** — no active spinning-reserve constraint currently, despite the column suggesting one is active.
- `[VERIFY]` — **`load_trajectory=LOWDelEVs` (P0) demand assumptions** haven't been independently re-derived in this doc pass; confirm what differs from the earlier-referenced `IRP24_LOW`/`IRP24_MOD` trajectories before citing specific demand numbers in the paper.

---

## 8. Transmission Expansion

Existing corridors only — no new (non-existing) corridors modelled. Existing links: `p_nom` becomes `p_nom_min`, `p_nom_extendable=True`, `p_nom_max=inf`; the optimizer can add capacity on top.

**Cost formula:** `capital_cost [ZAR/MW/yr] = length [km] × length_factor (1.25) × (investment [ZAR/MW/km] × CRF + FOM_rate × investment)`, HVAC overhead investment 6,000 ZAR/MW/km, lifetime 40 yr, FOM 2%/yr → ~689 ZAR/MW/km/yr at 9.2% discount. Parameters live in `config.yaml::lines.hvac_overhead`.

**Known currency-conversion inconsistency (open, low-priority):** the 6,000 ZAR/MW/km figure traces to Hagspiel via `costs_pypsa-za.xlsx`'s `updated` sheet, which has it in EUR (400 EUR/MW/km, 2030). Everywhere else in the project, EUR costs go through `convert_cost_units()` using the project's `EUR_to_ZAR=17.83` (`config.yaml`). The transmission block is hard-coded in ZAR directly (`lines.hvac_overhead.investment: 6000`), implying an inconsistent 15.0 ZAR/EUR rate. At the correct 17.83 rate this should be ~7,132 ZAR/MW/km (~16% higher). Doesn't change the qualitative "no expansion is economic" finding below — it would make expansion even less attractive, not more.

**Why the optimizer doesn't expand even heavily-loaded corridors:** confirmed **not a bug** (see §3 cost-scaling note — this was originally mistaken for one). Several corridors run >95% loaded for hundreds to thousands of hours/year (e.g. Free State–Gauteng at 99.991% for 4,448h — over half the year), yet `p_nom_opt ≈ p_nom_min` (no real investment) in every scenario. After correcting for the ×1000 export scaling: the Free State–Gauteng corridor's congestion rent averages ~144,000 ZAR/MW/yr, well under its ~291,000 ZAR/MW/yr expansion cost. The network is a near-meshed 38-corridor transport model (no Kirchhoff constraints) between 10 regions, so high utilisation on one link doesn't necessarily mean the system captures much value from relieving it — flow can reroute cheaply. Existing capacity also already carries conservative buffers (St. Clair voltage-stability derating below thermal limit; N-1 security — for corridors with 2 parallel lines, the stronger line is assumed fully out, roughly halving capacity vs. thermal, not just the flat 30% single-line derate). None of this overturns the finding — it just means the reported "99.999% loaded" figures are against an already-conservative limit, not the physical maximum. **Only worth revisiting** (new corridors, Weg A exogenous via `transmission_expansion.xlsx` + `build_topology.py:106-133`, or Weg B endogenous candidate links in `base_network.py`) if the economics genuinely change — e.g. a single-period 2030-only run without the 2025 anchor period, which would raise the effective benefit/cost ratio for existing-corridor expansion from ~1.0 to ~1.56 (2025 currently dilutes the periods-weighted return since it has little congestion).

---

## 9. Code Modifications

All changes marked `# AM added` / `# AM adjusted` in source.

| File                             | Change                                                                                                                                                                                                                                                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `custom_constraints.py`        | `add_ct_reinvestment_constraint()` (P0, ≤2 periods) and `add_ct_reinvestment_constraint_multiyear()` (P1, >2 periods) — CT revenue recycling, see §5                                                                                                                                                                           |
| `prepare_and_solve_network.py` | CT reinvestment hook (auto-selects P0 vs P1 function by period count);`n.statistics()` wrapped in try/except (PyPSA 0.35.2 bug on certain configs); `set_extendable_limits_global()` corrects IRP cumulative targets to per-period net-new-build deltas via `electricity.existing_capacity_carriers` mapping in `config.yaml` |
| `_helpers.py`                  | Excel`TRUE`/`FALSE` string normalisation; `aggregate_costs()` multi-invest check fixed to `len(n.investment_periods) > 0` (PyPSA 0.35.x API change)                                                                                                                                                                           |
| `add_electricity.py`           | Multi-node renewable profile bus assignment fix (SIGSEGV, see §3);`update_transmission_costs()` computes extendable-link capital cost from `length` + `hvac_overhead` config                                                                                                                                                   |
| `base_network.py`              | Transmission expansion setup from`line_expansion` in SCENARIO_SETUP                                                                                                                                                                                                                                                                 |
| `build_topology.py`            | Column rename`capacity_expansion_years` → `simulation_years`                                                                                                                                                                                                                                                                     |
| `Snakefile`                    | `_R` dependency lambda (wait for base scenario's `solved.nc`); plot rules integrated into `solve_all`                                                                                                                                                                                                                           |
| `scripts/plot_network_sa.py`   | Map + cost-bar-chart plotting; carrier colours/nice-names in`config.yaml::plotting`; costs displayed as `×1000` (see §3 — this scaling is applied consistently at plot time, only the raw `solved.nc` export is unscaled)                                                                                                    |

Marginal costs for fixed (existing) wind/solar come from `variable_om_cost (R/MWh)` in `fixed_technologies.xlsx::renewables` — genuine VOM, not PPA tariffs (PPAs are capacity-based R/MW/yr and enter as capital/fixed cost). Since RE has no fuel cost, marginal cost ≈ VOM, near-zero.

---

## 10. Historical Calibration Results (superseded — reference only)

These results predate the 2026-09-13 changes in §3 (`override_coal_msl` was 0.4, not 0.65; unclear whether `unit_committment`/`endogenous_coal_decom` were active — **do not treat as representative of the current parameter state**). Kept only as a sanity-check reference for "does the model behave sensibly at all," and as a baseline to compare against once a fresh `LC-182h` or `LC` run completes under the current (§4) parameters.

**Configuration:** `regions=10`, `fixed_conventional=BASE_PMR1b`, `LC-182h` (97 snapshots total across 2 periods, weighted to 8760h/yr each), `override_coal_msl=0.4`, `extendable_max_annual=UNC`, `transmission_grid=existing+tdp`, `line_expansion=copt`. Analysis year 2030 (snapshot_weightings sum 8722h).

### Dispatch [TWh, 2030]

| Technology             | P0_BASE          | P0_CT            | P0_BASE_R        | P0_CT_R          |
| ---------------------- | ---------------- | ---------------- | ---------------- | ---------------- |
| Total coal             | 91.91            | 89.86            | 77.95            | 77.95            |
| Total solar            | 62.44            | 64.77            | 43.68            | 40.26            |
| Wind                   | 43.87            | 44.02            | 90.40            | 95.22            |
| CCGT                   | 8.52             | 8.31             | 0.00             | 0.00             |
| OCGT gas               | 22.38            | 22.38            | 22.38            | 22.38            |
| Nuclear                | 14.55            | 14.55            | 14.55            | 14.55            |
| **Total supply** | **258.38** | **258.61** | **263.68** | **265.08** |

### Emissions & CT Revenue [2030]

|                     | P0_BASE | P0_CT  | P0_BASE_R | P0_CT_R |
| ------------------- | ------- | ------ | --------- | ------- |
| Total CO₂ [MtCO₂] | 116.47  | 113.99 | 101.72    | 101.72  |
| CT revenue [bn ZAR] | —      | 52.66  | 53.81     | 46.99   |

**Key finding at the time (worth re-testing under current parameters):** P0_BASE_R and P0_CT_R were numerically near-identical — the reinvestment constraint's floor dominated, and the CT price signal added almost nothing on top of it, because CT only reduced BASE emissions by ~2.1% (MSL=0.4 kept coal near its floor already in most hours). This is a big part of the motivation for §3's endogenous-retirement change — daily MSL-driven floor effects are expected to matter less once retirement itself can respond to CT, and the effect should show up more clearly once `LC` (full 8760h) captures the daily solar cycle that creates MSL-free night hours.

**Transmission:** no expansion in any scenario even under these earlier settings — consistent with the economically-correct-non-expansion finding in §8.

---

## 11. Historical P1 Pathway Results (1-bus, LC-182h — last computed, before P1 was set inactive)

Computed under `regions=1`, `override_coal_msl=0.4`, `coal_ramp_rate_multiplier=1.5`, `unit_committment=0`, `extendable_min_total=UNC`, `carbon_tax=CT_2050` — these specific parameters broadly still match the current (inactive) P1 row in §4, so this table is a reasonable reference for what a P1 rerun would look like, **not** a guarantee (rerun before citing in a paper).

| Period | P0_BASE Coal[GW] | Wind[GW] | Solar[GW] | Storage[GW] | Coal[TWh] | RE share |
| ------ | ---------------- | -------- | --------- | ----------- | --------- | -------- |
| 2025   | 41.4             | 4.3      | 2.7       | 3.6         | 181.5     | 8.7%     |
| 2030   | 36.0             | 9.0      | 13.5      | 5.2         | 153.0     | 26.2%    |
| 2035   | 27.0             | 21.2     | 20.5      | 7.3         | 114.7     | 44.4%    |
| 2040   | 27.0             | 33.8     | 22.1      | 9.3         | 102.3     | 53.8%    |
| 2045   | 12.4             | 48.9     | 32.8      | 17.1        | 45.2      | 68.0%    |
| 2050   | 12.4             | 50.6     | 54.3      | 35.6        | 44.4      | 75.3%    |

*(P1_BASE shown; P1_BASE_R / P1_CT / P1_CT_R follow the same shape with progressively higher RE shares by 2050: BASE 75.3%, CT 87.2%, BASE_R 90.0%, CT_R 90.1% — recycling has a larger long-run effect than the price signal alone.)*

**Notable pattern (mechanism, not a bug):** coal capacity is identical across all 4 P1 scenarios in every period — by design, since `phased_decom` is fixed and `endogenous_coal_decom=0` for P1. CT therefore only ever affects *dispatch*, never *retirement timing*, in P1 as currently configured (unlike P0 since the §3 change). Investment is "lumpy" — large jumps at 2035 (when both a coal-retirement step and a CT-rate jump coincide) — an expected artifact of perfect-foresight optimization with `extendable_max_annual=UNC` (no ramp-rate cap on new build), not a bug.

---

## 12. Results Analysis Notebook

**File:** `paper0_results_analysis.ipynb`. Loads all four P0 `solved.nc` networks (`RESULTS_DIR="results/Coal_Flexibilisation"`), extracts the 2030 period via `get_2030()`, and produces: new-build capacity, generation mix, CO₂ emissions, CT revenue vs. reinvestment, system costs, and a summary CSV (`paper_summary_2030_182h.csv`).

**Running on the server via VS Code + SSH:**

```bash
# one-time kernel registration
/home/users/a/agma/.pixi/envs/pypsa-rsa/bin/python -m ipykernel install --user --name pypsa-rsa --display-name "PyPSA-RSA"

# each session — start Jupyter on the server
nohup /home/users/a/agma/.pixi/envs/pypsa-rsa/bin/jupyter lab --no-browser --port=8899 > ~/jupyter.log 2>&1 &
cat ~/jupyter.log   # copy the http://localhost:8899/lab?token=... URL
```

In VS Code: open the notebook → kernel picker → "Jupyter Server" → "Existing Jupyter Server..." → paste the URL → select the "PyPSA-RSA" kernel. VS Code Remote SSH forwards the port automatically. Stop with `pkill -f "jupyter lab"`.

---

## 13. How to Run

### Before every run — checklist

- [ ] `run_scenario` flags correct in `scenarios_to_run.xlsx` (currently: P0 rows `true`, P1 rows `False`)
- [ ] `options`: `LC` for production, or an explicit test resolution (`LC-182h`, `LC-2190h`, ...) for a quick check — see §6 for what each actually does
- [ ] `regions`: 10 for P0, 1 for P1
- [ ] Any of `unit_committment` / `endogenous_coal_decom` / `variable_storage_vom` that get changed: filled with `0`, never blank (§7)

### Production runs — `run_head.job` (frontend + SLURM child jobs)

**Never `sbatch run_head.job`.** The head Snakemake process must run on the frontend — it submits each rule as its own SLURM child job via `--executor slurm`. Submitting the head itself via sbatch creates a Gurobi session on a compute node (counts against the WLS license) and gets killed if that job's own walltime runs out.

```bash
tmux new -s pypsa           # start a persistent session
bash /beegfs/scratch/agma/pypsa-rsa/run_head.job
# Ctrl+B  D   to detach (keeps running after logout)
```

Current `run_head.job` settings: `runtime=20000` min (~13.9 days, under the 14-day SLURM max), `mem_mb=16000` default (solve rule overrides higher), `solver_slots=2` (max 2 concurrent Gurobi sessions — matches the WLS academic baseline), `--jobs 16` (max concurrent SLURM child jobs), `--latency-wait 120` (BeeGFS output-file lag), `-F` (force rerun all — needed after switching `options`, e.g. `LC-182h → LC`; safe to drop once a clean `LC` run has completed and only incremental reruns are needed).

DAG shape: preprocessing (`build_topology → base_network → add_electricity`) runs for all active scenarios in parallel first (minutes). Then solves run in waves — `P0_BASE`/`P0_CT` (and `P1_BASE`/`P1_CT` if active) first, `_R` variants wait for their base scenario's `solved.nc`. Plots submit automatically after each scenario finishes.

### Quick/test runs — `run_p0.job` (single SLURM allocation, no `--executor slurm`)

```bash
sbatch run_p0.job
```

Current settings: `--time=14-00:00:00 --mem=200G --cpus-per-task=32`, runs `micromamba run --root-prefix /beegfs/home/users/a/agma/.local/share/mamba -p /beegfs/home/users/a/agma/.pixi/envs/pypsa-rsa snakemake solve_all -j 4 -F --resources solver_slots=2`, includes an hourly heartbeat (`--- HOURLY UPDATE ---`) written to the log to distinguish an active run from a hung one.

**Everything (preprocessing + all 4 solves) shares this one allocation** — fine for small test resolutions (`LC-182h`, `LC-2190h`) where the whole pipeline is lightweight, but **do not reuse this script for a full `LC` (8760h) production run**: four 8760h solves competing for one 200GB/32CPU allocation risks the same class of OOM failure documented for the June 2026 incident (a single 8760h solve needed `mem_mb=200000` on its own once raised). Use `run_head.job` for production instead.

### Monitoring

```bash
squeue --me                                    # all running child/test jobs
tmux attach -t pypsa                           # live snakemake output (production)
tail -f logs/slurm_p0_<jobid>.out              # test-run log
tail -f $(ls -t logs/snakemake_head_*.log | head -1)   # production head log (latest)
```

### Cancelling

```bash
tmux attach -t pypsa   # then Ctrl+C to stop the head process
# or
tmux kill-session -t pypsa
scancel $(squeue --me -h -o "%i" | tr '\n' ' ')   # cancel all remaining child jobs
scancel <jobid>                                    # cancel one job (e.g. a test run)
```

### Results

```
results/Coal_Flexibilisation/{scenario}/{options}/networks/solved.nc
results/Coal_Flexibilisation/{scenario}/{options}/outputs/plots/{map_only,map_full,pathway}.png
results/Coal_Flexibilisation/{scenario}/{options}/outputs/generators.csv
```

`{options}` is a literal path component (`Snakefile`) — a test run at e.g. `LC-2190h` lands in a separate subfolder from `LC` production results automatically, so a coarse test does **not** overwrite production output as long as the test doesn't also use `options=LC`. (An earlier doc draft recommended a separate `working_folder` for this reason — not strictly necessary given the `{options}` path segment, but still useful when a fully separate results tree is wanted for exploratory/debugging runs.)

Download: `scp -r agma@gateway.hpc.tu-berlin.de:/beegfs/scratch/agma/pypsa-rsa/results ~/Downloads/`

### Gurobi WLS: stuck sessions ("Overage for too long")

**Symptom:** every solve fails immediately with `GurobiError: Overage for too long, N active sessions...` even though `squeue --me` is empty. **Cause:** a SLURM job was killed (OOM, timeout, Ctrl+C) without Gurobi releasing its WLS session. **Fix:** log in at `https://license.gurobi.com`, find WLS license ID `938810` → Active Sessions → terminate all. **Verify clear:**

```bash
export GRB_LICENSE_FILE=/home/users/a/agma/gurobi.lic
python3 -c "import gurobipy; m = gurobipy.Model(); print('Gurobi OK')"
```

**Prevention:** always keep `--resources solver_slots=2` (matches the 2-session WLS academic baseline). Known remaining risk (not yet fixed): every SLURM job — even non-solve preprocessing jobs — briefly opens/closes a WLS session via PuLP's `pulp.listSolvers(onlyAvailable=True)` at Snakemake startup; with many jobs starting simultaneously this can transiently push the count above 2. Low probability, not zero. Possible fixes not yet applied: drop to `solver_slots=1`, or scope `GRB_LICENSE_FILE` to only the actual solve step instead of the whole job shell.
