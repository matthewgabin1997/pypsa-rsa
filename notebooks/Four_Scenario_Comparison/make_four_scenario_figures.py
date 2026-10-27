"""Four-scenario comparison figures: REF-LC, POL-3GW, POL-6GW, POL-18.25GW (1 node, LC-182h development runs).

Read-only with respect to the model: loads the four saved solved networks (+ outputs/*.csv) and writes PNG/PDF figures,
per-figure data CSVs and a contact sheet into this folder (notebooks/Four_Scenario_Comparison/), overwriting the previous
outputs. No model input or result is modified. Cost figures use the term-by-term objective reconstruction (T1-T6, see
objective_terms.py) that reproduces n.objective exactly, not n.statistics. 24 values are checked against previously
verified results before any figure is written; the script stops if any check fails.

Run from anywhere (paths are resolved relative to this file), in the pypsa-rsa conda environment:
    ~/miniforge3/envs/pypsa-rsa/bin/python notebooks/Four_Scenario_Comparison/make_four_scenario_figures.py
Requires the Git-ignored results of REF-LC, POL-3GW, POL-6GW and POL-18.25GW (see README.md).
"""
import logging
import os
import sys
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pypsa  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(OUT, "..", "..")) + os.sep  # repository root
sys.path.insert(0, OUT)  # so objective_terms imports even under `python -I`
from objective_terms import load, terms  # noqa: E402  (verified objective reconstruction)
SC = ["REF-LC", "POL-3GW", "POL-6GW", "POL-18.25GW"]
POL = SC[1:]
SC_COL = {"REF-LC": "#7a7974", "POL-3GW": "#86b6ef", "POL-6GW": "#2a78d6", "POL-18.25GW": "#104281"}  # validated: grey + ordinal blue ramp
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]  # validated categorical order
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
CONV = {"ocgt_gas_h2_40": 2040, "ocgt_gas_h2_45": 2045, "ocgt_gas_h2_50": 2050, "ocgt_gas_h2_55": 2055, "ocgt_gas_h2_60": 2060}
CT = pd.read_excel(REPO + "scenarios/Coal_Flexibilisation/sub_scenarios/emissions.xlsx", sheet_name="carbon_tax", index_col=0).loc["CT_2050"]
SOURCE = ("Source: PyPSA-RSA gas-to-power study, saved solved networks (REF-LC 22 Oct 2026; POL runs 27 Oct 2026), "
          "commit db90bff. 1-node, LC-182h development results - not hourly-resolution findings.")

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "font.size": 9.5,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
    "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "lines.linewidth": 2,
    "pdf.fonttype": 42, "savefig.dpi": 300,
})

# ---------------------------------------------------------------- data
N = {s: load(s) for s in SC}
n0 = N["REF-LC"][0]
P = list(n0.investment_periods)
WG = n0.snapshot_weightings.generators            # represented hours per snapshot (annual energy)
HRS = WG.groupby(level=0).sum()
for s in SC:
    assert N[s][0].snapshot_weightings.equals(n0.snapshot_weightings) and N[s][0].investment_period_weightings.equals(n0.investment_period_weightings)


def active(n, c, y):
    return n.get_active_assets(c, y)


def cap_val(df):
    return pd.Series(np.where(df.p_nom_extendable, df.p_nom_opt, df.p_nom), index=df.index)


def energy(n):
    return n.generators_t.p.mul(WG, axis=0).groupby(level=0).sum()  # MWh/yr per generator


TECH = [("Coal", lambda c: c in ("coal", "sasol_coal")),
        ("Solar PV", lambda c: c.startswith("solar_pv")),
        ("Wind", lambda c: c.startswith("wind")),
        ("Nuclear", lambda c: c == "nuclear"),
        ("Hydro & imports", lambda c: c in ("hydro", "hydro_import")),
        ("Storage (PHS, batteries)", lambda c: c == "phs" or c.startswith("battery")),
        ("OCGT-class + CCGT steam", lambda c: c.startswith("ocgt") or c == "ccgt_steam"),
        ("Other (bio, CSP, RMIPPP, Sasol gas)", lambda c: c in ("bioenergy", "solar_csp", "rmippp", "sasol_gas"))]


def tech_of(c):
    for name, f in TECH:
        if f(c):
            return name
    return None


def capacity_by_tech(n):
    out = {}
    for comp in ("Generator", "StorageUnit"):
        df = n.df(comp)
        for y in P:
            a = df[active(n, comp, y)]
            a = a[a.carrier != "load_shedding"]
            v = cap_val(a).groupby(a.carrier.map(tech_of)).sum() / 1e3
            for k, x in v.items():
                out.setdefault(k, {}).setdefault(y, 0.0)
                out[k][y] += x
    return pd.DataFrame(out).T.reindex([t for t, _ in TECH]).fillna(0)[P]


def ocgt_group(row):
    c = row.carrier
    if c == "ocgt_gas":
        return "Natural-gas OCGT (new)"
    if c in CONV:
        return "H2-ready OCGT (new)"
    if c == "ocgt_diesel":
        return "Diesel OCGT (new)" if row.p_nom_extendable else "Diesel OCGT (existing)"
    if c == "ccgt_steam":
        return "CCGT steam (new)"
    return None


OGRP = ["Natural-gas OCGT (new)", "H2-ready OCGT (new)", "Diesel OCGT (new)", "Diesel OCGT (existing)", "CCGT steam (new)"]


def ocgt_capacity(n):
    g = n.generators
    grp = g.apply(ocgt_group, axis=1)
    out = {}
    for y in P:
        a = active(n, "Generator", y) & grp.notna()
        out[y] = cap_val(g[a]).groupby(grp[a]).sum() / 1e3
    return pd.DataFrame(out).reindex(OGRP).fillna(0)


def gas_metrics(n):
    """Per period: natural-gas-burning OCGT capacity/generation split into natural-gas OCGT and H2-ready-before-conversion,
    steam, natural-gas fuel (PJ), capacity factors. Steam consumes no fuel."""
    g, e = n.generators, energy(n)
    rows = {}
    for y in P:
        act = active(n, "Generator", y)
        ng = g.index[act & (g.carrier == "ocgt_gas")]
        h2g = g.index[act & g.carrier.isin([c for c, cy in CONV.items() if y < cy])]
        st = g.index[act & (g.carrier == "ccgt_steam")]
        sas = g.index[act & (g.carrier == "sasol_gas")]
        r = {"ngOCGT_GW": cap_val(g.loc[ng]).sum() / 1e3, "ngOCGT_TWh": e.loc[y, ng].sum() / 1e6,
             "h2onGas_GW": cap_val(g.loc[h2g]).sum() / 1e3, "h2onGas_TWh": e.loc[y, h2g].sum() / 1e6,
             "steam_GW": cap_val(g.loc[st]).sum() / 1e3, "steam_TWh": e.loc[y, st].sum() / 1e6}
        burn = list(ng) + list(h2g) + list(sas)
        r["NGfuel_PJ"] = float((e.loc[y, burn] / g.loc[burn, "efficiency"]).sum() * 3.6 / 1e6)
        for k in ("ngOCGT", "h2onGas", "steam"):
            r[f"{k}_CF%"] = 100 * r[f"{k}_TWh"] * 1e6 / (r[f"{k}_GW"] * 1e3 * HRS[y]) if r[f"{k}_GW"] > 0 else np.nan
        fl_gw, fl_twh = r["ngOCGT_GW"] + r["h2onGas_GW"], r["ngOCGT_TWh"] + r["h2onGas_TWh"]
        r["gasFleet_GW"], r["gasFleet_TWh"] = fl_gw, fl_twh
        r["gasFleet_CF%"] = 100 * fl_twh * 1e6 / (fl_gw * 1e3 * HRS[y]) if fl_gw > 0 else np.nan
        rows[y] = r
    return pd.DataFrame(rows).T


def coal_co2(s):
    n, ret = N[s]
    cg = n.generators[(n.generators.carrier == "coal") & ~n.generators.p_nom_extendable]
    op, rt = {}, {}
    for y in P:
        a = cg.index[active(n, "Generator", y)[cg.index]]
        life = cg.loc[a, "p_nom"].sum()
        r = sum(cg.at[g_, "p_nom"] * sum(ret.get(f"{g_}_{yy}", 0) for yy in P if 2030 <= yy <= y) for g_ in a)
        op[y], rt[y] = (life - r) / 1e3, r / 1e3
    f = pd.read_csv(REPO + f"results/Coal_Flexibilisation/{s}/LC-182h/outputs/generator_emissions.csv", index_col=0)
    e = energy(n)
    co2 = (e * f.reindex(index=e.index, columns=e.columns).fillna(0)).sum(axis=1) / 1e9
    return pd.Series(op), pd.Series(rt), co2


def carbon_pv(s):
    n = N[s][0]
    f = pd.read_csv(REPO + f"results/Coal_Flexibilisation/{s}/LC-182h/outputs/generator_emissions.csv", index_col=0)
    wt = n.snapshot_weightings["objective"].mul(n.investment_period_weightings["objective"], level=0)
    e = n.generators_t.p.mul(wt, axis=0).groupby(level=0).sum()
    cov = [c for c in e.columns if c in f.columns]
    return float(((e[cov] * f.reindex(index=e.index)[cov]).sum(axis=1) / 1e3 * pd.Series({y: float(CT[y]) for y in e.index}) / 1e3).sum())


CAP = {s: capacity_by_tech(N[s][0]) for s in SC}
OCAP = {s: ocgt_capacity(N[s][0]) for s in SC}
GAS = {s: gas_metrics(N[s][0]) for s in SC}
CC = {s: coal_co2(s) for s in SC}
TERMS = {s: terms(*N[s])[0] for s in SC}
CARB = {s: carbon_pv(s) for s in SC}
OBJ = {s: N[s][0].objective for s in SC}
FLOORS = {"POL-3GW": {("ocgt_gas", 2030): 2102, ("ccgt_steam", 2030): 898},
          "POL-6GW": {("ocgt_gas", 2030): 4205, ("ccgt_steam", 2030): 1795},
          "POL-18.25GW": {("ocgt_gas", 2030): 4205, ("ocgt_gas", 2035): 4205, ("ocgt_gas", 2040): 4029, ("ocgt_gas", 2045): 350,
                          ("ccgt_steam", 2030): 1795, ("ccgt_steam", 2035): 1795, ("ccgt_steam", 2040): 1721, ("ccgt_steam", 2045): 150}}


def vintage_build(n, carrier):
    g = n.generators[(n.generators.carrier == carrier) & n.generators.p_nom_extendable]
    return g.p_nom_opt.groupby(g.build_year).sum().reindex(P).fillna(0)


VB = {s: {c: vintage_build(N[s][0], c) for c in ("ocgt_gas", "ccgt_steam")} for s in SC}

# ---------------------------------------------------------------- validation against previously verified numbers
EXPECT = [
    ("objective REF-LC", OBJ["REF-LC"], 2674004460.5, 1), ("objective POL-3GW", OBJ["POL-3GW"], 2673994974.1, 1),
    ("objective POL-6GW", OBJ["POL-6GW"], 2674063148.9, 1), ("objective POL-18.25GW", OBJ["POL-18.25GW"], 2675043929.5, 1),
    ("dObj POL-6GW", OBJ["POL-6GW"] - OBJ["REF-LC"], 58688, 1), ("dObj POL-18.25GW", OBJ["POL-18.25GW"] - OBJ["REF-LC"], 1039469, 1),
    ("dT1 POL-18.25GW", TERMS["POL-18.25GW"].iloc[0] - TERMS["REF-LC"].iloc[0], 6801118, 2),
    ("dT5 POL-6GW", TERMS["POL-6GW"].iloc[4] - TERMS["REF-LC"].iloc[4], -2217001, 2),
    ("dCarbon POL-6GW", CARB["POL-6GW"] - CARB["REF-LC"], -3500052, 2), ("dCarbon POL-18.25GW", CARB["POL-18.25GW"] - CARB["REF-LC"], -2629085, 2),
    ("OCGT-class+steam 2050 GW (all)", min(OCAP[s][2050].sum() for s in SC), 47.13, 0.01),
    ("NG OCGT GW 2050 POL-18.25GW", GAS["POL-18.25GW"].at[2050, "ngOCGT_GW"], 19.207, 0.001),
    ("NG OCGT CF 2050 REF-LC %", GAS["REF-LC"].at[2050, "ngOCGT_CF%"], 6.995, 0.002),
    ("NG OCGT CF 2050 POL-18.25GW %", GAS["POL-18.25GW"].at[2050, "ngOCGT_CF%"], 3.907, 0.002),
    ("NG fuel 2030 REF-LC PJ", GAS["REF-LC"].at[2030, "NGfuel_PJ"], 62.49, 0.01), ("NG fuel 2035 POL-18.25GW PJ", GAS["POL-18.25GW"].at[2035, "NGfuel_PJ"], 96.57, 0.01),
    ("NG fuel 2050 REF-LC PJ", GAS["REF-LC"].at[2050, "NGfuel_PJ"], 61.08, 0.01),
    ("gas fleet CF 2030 REF-LC %", GAS["REF-LC"].at[2030, "gasFleet_CF%"], 6.06, 0.02),
    ("steam TWh 2030 POL-6GW", GAS["POL-6GW"].at[2030, "steam_TWh"], 3.155, 0.001),
    ("CO2 2030 REF-LC Mt", CC["REF-LC"][2][2030], 51.51, 0.01), ("CO2 2030 POL-6GW Mt", CC["POL-6GW"][2][2030], 48.83, 0.01),
    ("coal operating 2030 POL-18.25GW GW", CC["POL-18.25GW"][0][2030], 8.69, 0.01),
    ("steam 2040 vintage POL-18.25GW MW", VB["POL-18.25GW"]["ccgt_steam"][2040], 1721.0, 0.1),
    ("NG OCGT 2030 vintage POL-6GW MW", VB["POL-6GW"]["ocgt_gas"][2030], 4736.2, 0.1),
]
bad = [(k, v, e) for k, v, e, tol in EXPECT if abs(v - e) > tol]
print("VALIDATION:", "all %d checks match previously verified values" % len(EXPECT) if not bad else f"MISMATCH {bad}")
if bad:
    sys.exit(1)
print("reconstruction residuals (kZAR):", {s: round(float(TERMS[s].iloc[-1]), 3) for s in SC})


# ---------------------------------------------------------------- helpers
def finish(fig, name, title, subtitle, data=None, note=None):
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", y=0.995)
    fig.text(0.01, 0.948, subtitle, ha="left", va="top", fontsize=9.5, color=INK2)
    foot = SOURCE + ("\n" + note if note else "")
    fig.text(0.01, 0.005, foot, ha="left", va="bottom", fontsize=7.2, color=INK2, wrap=True)
    fig.savefig(os.path.join(OUT, f"{name}.png"), dpi=300)
    fig.savefig(os.path.join(OUT, f"{name}.pdf"), metadata={"CreationDate": None})  # deterministic PDF (no timestamp)
    plt.close(fig)
    if data is not None:
        data.to_csv(os.path.join(OUT, f"{name}_data.csv"))
    print("wrote", name)


def gap_bars(ax, x, h, bottom, color, width, label=None):
    return ax.bar(x, h, width, bottom=bottom, color=color, edgecolor=SURF, linewidth=0.8, label=label)


def scen_legend(ax, loc="upper left", **kw):
    hs = [plt.Rectangle((0, 0), 1, 1, color=SC_COL[s]) for s in SC]
    ax.legend(hs, SC, loc=loc, ncol=4, fontsize=8.5, handlelength=1.2, **kw)


# ---------------------------------------------------------------- Fig 1: installed capacity by technology
fig, axs = plt.subplots(1, 4, figsize=(13, 5.2), sharey=True)
x = np.arange(len(P))
rows = []
for ax, s in zip(axs, SC):
    bot = np.zeros(len(P))
    for i, (t, _) in enumerate(TECH):
        v = CAP[s].loc[t].values
        gap_bars(ax, x, v, bot, CAT[i], 0.72, label=t)
        bot += v
        rows += [{"scenario": s, "technology": t, "period": y, "GW": vv} for y, vv in zip(P, v)]
    for xi, tot in zip(x, bot):
        ax.text(xi, tot + 2, f"{tot:.0f}", ha="center", va="bottom", fontsize=7.5, color=INK2)
    ax.set_title(s)
    ax.set_xticks(x, P)
    ax.set_xlabel("Investment period")
axs[0].set_ylabel("Installed capacity in operation (GW)")
axs[0].set_ylim(0, 245)
h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=4, fontsize=8.5, bbox_to_anchor=(0.5, 0.065))
fig.subplots_adjust(left=0.055, right=0.995, top=0.85, bottom=0.27, wspace=0.08)
finish(fig, "fig1_installed_capacity_by_technology", "Installed generating capacity by technology and investment period",
       "Capacity in operation in each period (not additions). Totals labelled. The four scenarios differ by < 1 GW in total in every period.",
       pd.DataFrame(rows).set_index(["scenario", "technology", "period"]),
       "Storage in GW of power capacity. OCGT-class + CCGT steam is split by carrier in Figure 2.")

# ---------------------------------------------------------------- Fig 2: OCGT-class + steam by carrier
fig, axs = plt.subplots(1, 4, figsize=(13, 5.0), sharey=True)
OCOL = {"Natural-gas OCGT (new)": CAT[0], "H2-ready OCGT (new)": CAT[1], "Diesel OCGT (new)": CAT[2], "Diesel OCGT (existing)": CAT[3], "CCGT steam (new)": CAT[4]}
rows = []
for ax, s in zip(axs, SC):
    bot = np.zeros(len(P))
    for gname in OGRP:
        v = OCAP[s].loc[gname].values
        gap_bars(ax, x, v, bot, OCOL[gname], 0.72, label=gname)
        bot += v
        rows += [{"scenario": s, "group": gname, "period": y, "GW": vv} for y, vv in zip(P, v)]
    for xi, tot in zip(x, bot):
        ax.text(xi, tot + 0.6, f"{tot:.1f}", ha="center", va="bottom", fontsize=7.5, color=INK2)
    ax.set_title(s)
    ax.set_xticks(x, P)
    ax.set_xlabel("Investment period")
axs[0].set_ylabel("Installed capacity in operation (GW)")
axs[0].set_ylim(0, 54)
h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=5, fontsize=8.5, bbox_to_anchor=(0.5, 0.075))
fig.subplots_adjust(left=0.055, right=0.995, top=0.85, bottom=0.25, wspace=0.08)
finish(fig, "fig2_ocgt_class_and_steam_by_carrier", "Peaking capacity: OCGT-class and CCGT steam by carrier",
       "Totals are identical in all scenarios from 2035 (47.13 GW in 2050). Mandated natural-gas OCGT replaces H2-ready and diesel OCGTs; steam is the binding addition.",
       pd.DataFrame(rows).set_index(["scenario", "group", "period"]),
       "Natural-gas, H2-ready and new-diesel OCGTs share capex, fixed O&M and efficiency (fuel identical until H2 conversion), so the split between them is "
       "near-degenerate; totals are robust. CCGT = separate gas-turbine and steam generators linked only by steam output <= 0.427 x OCGT output.")

# ---------------------------------------------------------------- Fig 3: gas capacity vs generation, 2030 and 2050
fig, axs = plt.subplots(2, 2, figsize=(11.5, 7.6), sharex=True)
comp = [("ngOCGT", "Natural-gas OCGT", CAT[0]), ("h2onGas", "H2-ready OCGT burning natural gas (before conversion)", CAT[1]), ("steam", "CCGT steam (no fuel)", CAT[4])]
xs = np.arange(len(SC))
rows = []
for j, y in enumerate((2030, 2050)):
    for i, (unit, lab) in enumerate((("GW", "Installed capacity (GW)"), ("TWh", "Electricity generation (TWh/yr)"))):
        ax = axs[i, j]
        bot = np.zeros(len(SC))
        for k, name, col in comp:
            v = np.array([GAS[s].at[y, f"{k}_{unit}"] for s in SC])
            gap_bars(ax, xs, v, bot, col, 0.6, label=name)
            bot += v
            rows += [{"year": y, "measure": unit, "component": name, "scenario": s, "value": vv} for s, vv in zip(SC, v)]
        for xi, tot in zip(xs, bot):
            ax.text(xi, tot * 1.01 + (0.3 if unit == "GW" else 0.1), f"{tot:.1f}", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_ylabel(lab)
        ax.set_title(f"{y}: {'capacity' if unit == 'GW' else 'generation'}")
        ax.set_ylim(0, (27 if unit == "GW" else 11.5))
        ax.set_xticks(xs, SC)
h, l = axs[0, 0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=3, fontsize=8.5, bbox_to_anchor=(0.5, 0.06))
fig.subplots_adjust(left=0.07, right=0.99, top=0.87, bottom=0.17, hspace=0.3, wspace=0.18)
finish(fig, "fig3_gas_capacity_vs_generation_2030_2050", "Natural-gas-fired capacity versus generation, 2030 and 2050",
       "Mandates raise gas-burning capacity but leave gas-fired generation almost unchanged: 6.6-7.4 TWh (2030) and 6.45 TWh (2050) from the OCGTs in every scenario.",
       pd.DataFrame(rows).set_index(["year", "measure", "component", "scenario"]),
       "OCGT and steam generation are modelled components, not paired CCGT plants. Steam burns no fuel; all of its feed-gas came from natural-gas-fired OCGT output "
       "in these runs (diesel and converted H2 units do not run). By 2050 every H2-ready unit has converted and none runs.")

# ---------------------------------------------------------------- Fig 4: natural-gas fuel and capacity factors across the horizon
fig, axs = plt.subplots(1, 3, figsize=(13, 4.8))
specs = [("NGfuel_PJ", "Natural-gas fuel consumption (PJ/yr)", "a. Natural-gas fuel use"),
         ("gasFleet_CF%", "Capacity factor (%)", "b. Gas-burning OCGT fleet CF"),
         ("steam_CF%", "Capacity factor (%)", "c. CCGT steam CF")]
yrs = P[1:]
rows = []
for ax, (col, ylab, ttl) in zip(axs, specs):
    for s in SC:
        v = GAS[s].loc[yrs, col].values
        ax.plot(yrs, v, color=SC_COL[s], marker="o", markersize=5, label=s)
        rows += [{"metric": col, "scenario": s, "period": y, "value": vv} for y, vv in zip(yrs, v)]
    ax.set_title(ttl, fontsize=9.8)
    ax.set_ylabel(ylab)
    ax.set_xticks(yrs)
    ax.set_xlabel("Investment period")
    ax.set_ylim(0, None)
axs[0].set_ylim(0, 110)
fig.legend([plt.Line2D([0], [0], color=SC_COL[s], marker="o") for s in SC], SC, loc="lower center", ncol=4, fontsize=8.5, bbox_to_anchor=(0.5, 0.1))
fig.subplots_adjust(left=0.05, right=0.995, top=0.8, bottom=0.3, wspace=0.25)
finish(fig, "fig4_gas_fuel_and_capacity_factors", "Natural-gas use and utilisation across the transition",
       "Fuel use peaks in 2035 (~96 PJ) and is almost identical across scenarios; capacity factors fall where mandates add capacity (lines overlap where scenarios coincide).",
       pd.DataFrame(rows).set_index(["metric", "scenario", "period"]),
       "Fuel = output / efficiency x 3.6 GJ/MWh for units burning natural gas in that period (natural-gas OCGT; H2-ready OCGT before its conversion year; Sasol gas = 0). "
       "Steam burns no fuel. CF = annual energy / (capacity in operation x represented hours, 8,594-8,722 h). 2025 omitted (no new gas). LC-182h CFs are indicative only.")

# ---------------------------------------------------------------- Fig 5: vintage additions vs policy minimums
fig, axs = plt.subplots(1, 2, figsize=(13, 4.9), sharey=True)
vy = P[1:]
w = 0.2
rows = []
for ax, (carrier, ttl) in zip(axs, (("ocgt_gas", "a. Natural-gas OCGT additions by build vintage"), ("ccgt_steam", "b. CCGT steam additions by build vintage"))):
    for k, s in enumerate(SC):
        xx = np.arange(len(vy)) + (k - 1.5) * w
        v = VB[s][carrier].loc[vy].values / 1e3
        ax.bar(xx, v, w * 0.92, color=SC_COL[s], label=s)
        for xi, y in zip(xx, vy):
            f = FLOORS.get(s, {}).get((carrier, y))
            if f:
                ax.plot([xi - w * 0.46, xi + w * 0.46], [f / 1e3, f / 1e3], color=INK, linewidth=1.6, solid_capstyle="butt")
            rows.append({"carrier": carrier, "scenario": s, "vintage": y, "built_GW": VB[s][carrier][y] / 1e3,
                         "policy_minimum_GW": (f / 1e3 if f else np.nan)})
    ax.set_xticks(np.arange(len(vy)), vy)
    ax.set_title(ttl, fontsize=9.8)
    ax.set_xlabel("Build vintage (new capacity commissioned in the period)")
axs[0].set_ylabel("New capacity added in the vintage (GW)")
hs = [plt.Rectangle((0, 0), 1, 1, color=SC_COL[s]) for s in SC] + [plt.Line2D([0], [0], color=INK, linewidth=1.6)]
fig.legend(hs, SC + ["Policy minimum for that scenario"], loc="lower center", fontsize=8.5, ncol=5, bbox_to_anchor=(0.5, 0.1))
fig.subplots_adjust(left=0.055, right=0.995, top=0.8, bottom=0.3, wspace=0.06)
finish(fig, "fig5_vintage_additions_vs_policy_minimums", "New gas-turbine and steam capacity by vintage: actual builds versus policy minimums",
       "Additions, not installed totals. Steam builds sit exactly at every POL-6GW and POL-18.25GW minimum (binding); natural-gas floors are met largely by substitution.",
       pd.DataFrame(rows).set_index(["carrier", "scenario", "vintage"]),
       "Black ticks = minimum-build requirement (extendable_technologies::min_annual_installed; 2041 IRP tranche counted in the 2045 vintage). "
       "Natural-gas OCGT additions above the floor replace identical H2-ready/diesel units; vintage-level splits are near-degenerate.")

# ---------------------------------------------------------------- Fig 6: coal and CO2
fig, axs = plt.subplots(1, 2, figsize=(13, 4.9))
w = 0.2
rows = []
for k, s in enumerate(SC):
    op, rt, co2 = CC[s]
    xx = np.arange(len(P)) + (k - 1.5) * w
    axs[0].bar(xx, op.values, w * 0.92, color=SC_COL[s], label=s)
    yy = P[1:]
    xx2 = np.arange(len(yy)) + (k - 1.5) * w
    axs[1].bar(xx2, co2.loc[yy].values, w * 0.92, color=SC_COL[s], label=s)
    rows += [{"scenario": s, "period": y, "coal_operating_GW": op[y], "coal_endogenously_retired_GW": rt[y], "CO2_Mt": co2[y]} for y in P]
axs[0].set_xticks(np.arange(len(P)), P)
axs[0].set_ylabel("Operating coal capacity (GW)")
axs[0].set_title("a. Existing coal still operating (after scheduled and endogenous retirement)", fontsize=9.8)
for k, s in enumerate(SC):
    axs[0].text(1 + (k - 1.5) * w, CC[s][0][2030] + 0.6, f"{CC[s][0][2030]:.2f}", ha="center", fontsize=7.2, color=INK2, rotation=90)
axs[1].set_xticks(np.arange(len(P[1:])), P[1:])
axs[1].set_ylabel("CO2 emissions (Mt/yr)")
axs[1].set_ylim(0, 62)
axs[1].set_title("b. Annual CO2 emissions (2025: 198.7 Mt in every scenario, not shown)", fontsize=9.8)
for k, s in enumerate(SC):
    axs[1].text(0 + (k - 1.5) * w, CC[s][2][2030] + 1, f"{CC[s][2][2030]:.1f}", ha="center", fontsize=7.2, color=INK2, rotation=90)
axs[0].set_xlabel("Investment period")
axs[1].set_xlabel("Investment period")
scen_legend(axs[0], loc="upper right")
fig.subplots_adjust(left=0.05, right=0.995, top=0.8, bottom=0.2, wspace=0.16)
finish(fig, "fig6_coal_and_co2", "Coal retirement and CO2 emissions",
       "Binding mandates bring forward Lethabo retirement in 2030 (+687 MW POL-6GW, +402 MW POL-18.25GW) and cut 2030 CO2 by 2.7 and 1.6 Mt; all coal is retired from 2035.",
       pd.DataFrame(rows).set_index(["scenario", "period"]),
       "CO2 = generation x outputs/generator_emissions.csv factors; stand-by emissions excluded. Coal stand-by costs are absent from the objective "
       "(unresolved review item), which may affect retirement timing in all scenarios.")

# ---------------------------------------------------------------- Fig 7: incremental cost decomposition
labels = ["New-build capex + fixed O&M (T1)", "Operating cost excl. carbon tax (T2 - carbon)", "Carbon tax (part of T2)",
          "Start-up / shut-down (T4)", "Coal-retirement fixed-O&M saving (T5)", "Net change in objective"]
dec = {}
for s in POL:
    d = TERMS[s] - TERMS["REF-LC"]
    dc = CARB[s] - CARB["REF-LC"]
    dec[s] = [d.iloc[0], d.iloc[1] - dc, dc, d.iloc[3], d.iloc[4], OBJ[s] - OBJ["REF-LC"]]
D = pd.DataFrame(dec, index=labels) / 1e6  # kZAR -> R bn
fig, ax = plt.subplots(figsize=(12, 5.4))
yb = np.arange(len(labels))[::-1]
h = 0.26
for k, s in enumerate(POL):
    yy = yb + (1 - k) * h
    ax.barh(yy, D[s].values, h * 0.9, color=SC_COL[s], label=s)
    for yi, v in zip(yy, D[s].values):
        if abs(v) > 0.05:
            ax.text(v + (0.08 if v >= 0 else -0.08), yi, f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=7.6, color=INK2)
ax.axvline(0, color=INK2, linewidth=1)
ax.set_yticks(yb, labels)
ax.set_xlabel("Change versus REF-LC (R billion, present value, 9.2% discount rate)")
ax.grid(axis="x", color=GRID)
ax.grid(axis="y", visible=False)
ax.set_xlim(-6.2, 8.2)
hs = [plt.Rectangle((0, 0), 1, 1, color=SC_COL[s]) for s in POL]
ax.legend(hs, POL, loc="lower right", fontsize=8.5)
fig.subplots_adjust(left=0.3, right=0.99, top=0.84, bottom=0.17)
finish(fig, "fig7_incremental_cost_decomposition", "Incremental system cost versus REF-LC by objective term",
       "Net costs are small (POL-6GW +R0.06 bn, POL-18.25GW +R1.04 bn PV) because higher capex is offset by carbon-tax, fuel and coal fixed-O&M savings.",
       D, "POL-3GW: every term < R0.02 bn (bars not visible; mandate non-binding). Terms rebuild the optimisation objective exactly (residual 0); n.statistics totals are not used (they omit T5). Carbon tax split from T2 using model "
          "emission factors and the CT_2050 path. T6 (retirement constant) is identical in all runs (0 change). Costs in kZAR in the model, shown here in R bn.")

# ---------------------------------------------------------------- Fig 8: vintage capacity factors (heatmap)
fig, axs = plt.subplots(2, 2, figsize=(13, 10.5))
axs = axs.flatten()
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("blue_seq", ["#f2f6fc", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
rows = []
for ax, s in zip(axs, SC):
    n = N[s][0]
    g, e = n.generators, energy(n)
    labs, M = [], []
    for c, nm in (("ocgt_gas", "Gas OCGT"), ("ccgt_steam", "Steam")):
        for i in g.index[(g.carrier == c) & g.p_nom_extendable]:
            capv = g.at[i, "p_nom_opt"]
            if capv < 10:
                continue
            by = int(g.at[i, "build_year"])
            r = [100 * e.at[y, i] / (capv * HRS[y]) if active(n, "Generator", y)[i] else np.nan for y in P[1:]]
            M.append(r)
            flo = FLOORS.get(s, {}).get((c, by))
            labs.append(f"{nm} {by}  ({capv:,.0f} MW){' *' if flo else ''}")
            rows += [{"scenario": s, "vintage": f"{nm} {by}", "MW": capv, "mandated_vintage": bool(flo), "period": y, "CF%": v} for y, v in zip(P[1:], r)]
    M = np.array(M, dtype=float)
    im = ax.imshow(np.ma.masked_invalid(M), cmap=cmap, vmin=0, vmax=30, aspect="auto")
    for (ri, ci), v in np.ndenumerate(M):
        if not np.isnan(v):
            ax.text(ci, ri, f"{v:.1f}", ha="center", va="center", fontsize=7.2, color="white" if v > 15 else INK)
    ax.set_xticks(range(len(P[1:])), P[1:])
    ax.set_yticks(range(len(labs)), labs, fontsize=7.6)
    ax.set_title(s)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
fig.subplots_adjust(left=0.16, right=0.98, top=0.9, bottom=0.17, wspace=0.62, hspace=0.22)
cax = fig.add_axes([0.3, 0.1, 0.4, 0.015])
cb = fig.colorbar(im, cax=cax, orientation="horizontal")
cb.set_label("Capacity factor of the vintage in each period (%); blank = not yet built", fontsize=8.5)
finish(fig, "fig8_vintage_capacity_factors", "Utilisation of individual gas-turbine and steam vintages",
       "Several vintages run below 1% (e.g. the 2030 natural-gas OCGT vintage in every scenario, including REF-LC). * = vintage with a policy minimum.",
       pd.DataFrame(rows).set_index(["scenario", "vintage", "period"]),
       "Low capacity factors are NOT evidence of economic stranding: these units earn reserve-margin capacity value (duals not saved), and dispatch among identical "
       "pre-conversion OCGT units is near-degenerate (which unit runs is arbitrary). Fleet-level utilisation (Figure 4) is the robust measure. LC-182h CFs are indicative only.")

# ---------------------------------------------------------------- Fig 9: total objective and incremental PV cost
fig, axs = plt.subplots(1, 2, figsize=(12.5, 4.8), gridspec_kw={"width_ratios": [1, 1.25]})
tot = np.array([OBJ[s] for s in SC]) / 1e9  # kZAR -> R trillion
axs[0].bar(np.arange(4), tot, 0.6, color=[SC_COL[s] for s in SC])
for i, v in enumerate(tot):
    axs[0].text(i, v + 0.02, f"{v:.4f}", ha="center", fontsize=8.5, color=INK2)
axs[0].set_xticks(np.arange(4), SC)
axs[0].set_ylabel("Total discounted system cost (R trillion PV)")
axs[0].set_ylim(0, 3.1)
axs[0].set_title("a. Optimisation objective (absolute)", fontsize=9.8)
inc = pd.DataFrame({"incl. carbon tax (model objective)": [(OBJ[s] - OBJ["REF-LC"]) / 1e6 for s in POL],
                    "excl. carbon tax (partial resource cost)": [((OBJ[s] - OBJ["REF-LC"]) - (CARB[s] - CARB["REF-LC"])) / 1e6 for s in POL]}, index=POL)
w = 0.36
for j, (col, hatch) in enumerate(((inc.columns[0], None), (inc.columns[1], "////"))):
    xx = np.arange(3) + (j - 0.5) * w
    axs[1].bar(xx, inc[col].values, w * 0.92, color=[SC_COL[s] for s in POL], hatch=hatch, edgecolor=SURF if hatch is None else "white", linewidth=0.6)
    for xi, v in zip(xx, inc[col].values):
        axs[1].text(xi, v + (0.06 if v >= 0 else -0.06), f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8.2, color=INK2)
axs[1].axhline(0, color=INK2, linewidth=1)
axs[1].set_xticks(np.arange(3), POL)
axs[1].set_ylabel("Incremental cost vs REF-LC (R billion PV)")
axs[1].set_ylim(-0.4, 4.3)
axs[1].set_title("b. Incremental present-value cost of each mandate", fontsize=9.8)
axs[1].legend([plt.Rectangle((0, 0), 1, 1, color="#6b6a66"), plt.Rectangle((0, 0), 1, 1, facecolor="#6b6a66", hatch="////", edgecolor="white")],
              list(inc.columns), loc="upper left", fontsize=8.5)
fig.subplots_adjust(left=0.07, right=0.995, top=0.8, bottom=0.22, wspace=0.22)
finish(fig, "fig9_objective_and_incremental_costs", "Total system cost and incremental cost of the gas mandates",
       "Objectives differ by at most 0.04%. Including carbon tax the mandates cost -R0.01 / +R0.06 / +R1.04 bn PV; excluding it about +R3.6-3.7 bn for POL-6GW and POL-18.25GW.",
       pd.concat([pd.Series(dict(zip(SC, tot)), name="objective_R_trillion"), inc], axis=1),
       "POL-3GW's -R9.5 m is within solver tolerance (final barrier gaps R6-14 m; REF-LC gap not stored). 'Excluding carbon tax' removes the carbon-tax payments "
       "(a transfer) and is a partial resource-cost comparison only, not a welfare assessment (no social cost of carbon; stand-by costs absent; T6 sign unresolved).")

# ---------------------------------------------------------------- contact sheet
names = sorted(f for f in os.listdir(OUT) if f.startswith("fig") and f.endswith(".png"))
fig, axs = plt.subplots(3, 3, figsize=(18, 11))
for ax, f in zip(axs.flat, names):
    ax.imshow(plt.imread(os.path.join(OUT, f)))
    ax.set_title(f.replace(".png", ""), fontsize=9)
    ax.axis("off")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "contact_sheet.png"), dpi=110)
print("wrote contact_sheet")
