# Four-scenario comparison figures — gas-to-power development runs

Nine figures comparing the four core scenarios of the PyPSA-RSA gas-to-power study. They are 1-node, LC-182h **development** runs (2025–2050).
The figures are produced read-only from the saved solved networks. The numbers are checked against previously verified results before any figure is written.

## Figures
| File | Content |
|---|---|
| `fig1_installed_capacity_by_technology` | Installed capacity (in operation) by technology group and investment period, one panel per scenario |
| `fig2_ocgt_class_and_steam_by_carrier` | Peaking capacity by carrier: natural-gas, H₂-ready, new/existing diesel OCGT and CCGT steam |
| `fig3_gas_capacity_vs_generation_2030_2050` | Gas-burning capacity vs. generation in 2030 and 2050 (natural-gas OCGT, H₂-ready burning gas before conversion, steam) |
| `fig4_gas_fuel_and_capacity_factors` | Natural-gas fuel use (PJ/yr), gas-burning OCGT fleet capacity factor, steam capacity factor, 2030–2050 |
| `fig5_vintage_additions_vs_policy_minimums` | New natural-gas OCGT and steam capacity per build vintage, with each scenario's minimum-build requirement |
| `fig6_coal_and_co2` | Existing coal still operating, and annual CO₂ emissions |
| `fig7_incremental_cost_decomposition` | Change vs. REF-LC by objective term: capex + fixed O&M, operating cost, carbon tax, start-ups, coal-retirement saving, net |
| `fig8_vintage_capacity_factors` | Capacity factor of each gas-turbine and steam vintage by period (heatmaps) |
| `fig9_objective_and_incremental_costs` | Total objective and incremental present-value cost, including and excluding carbon tax |

- Each figure is provided as a 300-dpi PNG and a vector PDF, plus `*_data.csv` holding the plotted values.
- `contact_sheet.png` previews all nine.

## Scenarios
All four use `scenarios/Coal_Flexibilisation`, with 1 node, `LC-182h`, investment periods 2025–2050, `NO_GAS_FLOOR`, `BASE` technologies, `DIESEL_LNG`, `RES_MRGN_10` / `BASE2`, `CT_2050`, `DELAYED_ESKOM_2035` and `LOWDelEVs`.
They differ only in the minimum-build label (`extendable_technologies.xlsx::min_annual_installed`):

| Scenario | Minimum-build requirement (gas turbine + steam) |
|---|---|
| REF-LC | none (least-cost reference) |
| POL-3GW | 2,102 + 898 MW in the 2030 vintage |
| POL-6GW | 4,205 + 1,795 MW in the 2030 vintage |
| POL-18.25GW | 6,000 / 6,000 / 5,750 / 500 MW in the 2030 / 2035 / 2040 / 2045 vintages (IRP 2025; 12,789 GT + 5,461 ST) |

## Files in this folder
- `make_four_scenario_figures.py` — computes all values, runs the 24 validation checks, and writes the figures, data CSVs and contact sheet into this folder (overwriting them).
- `objective_terms.py` — `load()` and `terms()`: rebuild the optimisation objective term by term (T1 capex, T2 operating incl. carbon tax, T3 stand-by, T4 start-up, T5/T6 coal retirement). This reproduces `n.objective` exactly. Cost figures use these terms, not `n.statistics`.
- `validate_palette.py` — standalone colour-accessibility check of the palettes used (Python port of the OKLab / Machado CVD checks). It is not needed to make the figures.

## How to regenerate
Requirements:
- the `pypsa-rsa` conda environment (PyPSA 0.35.2, pandas, NumPy, matplotlib, openpyxl);
- no Snakemake, Gurobi or optimisation is involved.

```bash
~/miniforge3/envs/pypsa-rsa/bin/python notebooks/Four_Scenario_Comparison/make_four_scenario_figures.py
```

- Paths are resolved relative to the script, so it can be run from any directory.
- PDFs are written without a creation timestamp, so re-running on unchanged inputs gives byte-identical files.

## Required inputs
| Input | Tracked in Git? |
|---|---|
| `results/Coal_Flexibilisation/{REF-LC,POL-3GW,POL-6GW,POL-18.25GW}/LC-182h/networks/solved.nc` | **no** (ignored) |
| `results/Coal_Flexibilisation/<scenario>/LC-182h/outputs/decom_status.csv` | **no** (ignored) |
| `results/Coal_Flexibilisation/<scenario>/LC-182h/outputs/generator_emissions.csv` | **no** (ignored) |
| `scenarios/Coal_Flexibilisation/sub_scenarios/emissions.xlsx` (`carbon_tax::CT_2050`) | yes |
| `scenarios/Coal_Flexibilisation/sub_scenarios/phased_decommissioning.xlsx` (`schedule::DELAYED_ESKOM_2035`) | yes |

**The simulation outputs are not on GitHub** (`results/`, `networks/` and `resources/` are Git-ignored). On a fresh clone, restore them before running the script.
- **Where they are:** the research archive `gas-policy-dev_2026-10-27`, i.e. `~/EnergyModels/archives/gas-policy-dev_2026-10-27/` or the copy of `gas-policy-dev_2026-10-27.tar.gz` on the Windows drive.
- **How to restore:** copy `repo/results/…` back into the repository's `results/`. The archive's `MANIFEST.sha256` lists the expected checksums.

Expected `solved.nc` SHA-256:

| Scenario | SHA-256 |
|---|---|
| REF-LC | `eefbafa82ce55c4031749495b8cb33f8ccfb6d529f8c40a369055e7aad580c33` |
| POL-3GW | `f7f49b8aac4a930a79b26c40abaad539005a5e52f1fff52cbecf826ab678bf72` |
| POL-6GW | `da4d65c94309929a2d97397f20a5d2f7895b8c0f7b2a40c3c1f625ba524559fa` |
| POL-18.25GW | `ce55196095ec261023e5023ed53d105a69330e2eca479c01ad43a97c5a223b05` |

## Limitations (development results, not final findings)
- **Temporal resolution.** LC-182h averages load and renewables over 182-hour blocks, so there is no daily cycle.
  - The reserve-margin peak is a block-mean peak.
  - Capacity factors, utilisation and stranding indicators are indicative only. They need hourly-resolution validation.
- **Single node.** No transmission or regional effects.
- **OCGT degeneracy.** Natural-gas, H₂-ready and new-diesel OCGTs share capex, fixed O&M and efficiency. H₂-ready units burn natural gas until their conversion year (2040/2045/2050); after that they are priced at diesel and emit nothing.
  - The split of capacity and dispatch between these carriers and vintages is near-arbitrary.
  - Only fleet totals are robust. Vintage capacity factors (Figure 8) are therefore not evidence of stranding.
- **Split CCGT.** Gas turbines (`ocgt_*`) and `ccgt_steam` are separate generators, linked only by steam output ≤ 0.427 × OCGT output.
  - There is no capacity pairing.
  - Steam gets a 1.0 reserve-margin credit.
  - Steam burns no fuel.
- **Low capacity factors ≠ stranded assets.** These units earn reserve-margin capacity value, but those duals are not saved, so economic stranding cannot be computed from these runs.
- **Costs.**
  - The objective is in kZAR, discounted at 9.2%.
  - It is a financial system cost that includes the carbon tax. The "excluding carbon tax" figure is only a partial resource-cost comparison, not a welfare assessment.
  - Coal stand-by costs are absent from the objective, and the coal-retirement constant (T6) has a sign that appears inverted. T6 is identical in all runs, so differences between scenarios are unaffected.
- **Solar near-degeneracy.** `solar_pv` and `solar_pv_low` have identical costs, so large but almost costless capacity swings can appear between scenarios.

## Provenance
- Code and inputs: branch `gas-policy-development-2026-10` of https://github.com/matthewgabin1997/pypsa-rsa, checkpoint commit `db90bff`.
- Figures generated 27 Oct 2026. The script was made path-independent on the same day; that change was verified to reproduce all 9 data CSVs and all 10 PNGs byte-identically.
