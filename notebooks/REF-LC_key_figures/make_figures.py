"""REF-LC key results: original (2026-10-06) vs corrected (2026-10-22) run.

Read-only: loads the two solved networks and decom_status.csv files, prints the
numbers quoted in notebooks/REF-LC_key_results_comparison_2026-10-26.md and writes
four PNG figures next to this script. It does not modify any model input or result
and does not run an optimisation.

Run from the repository root:
    ~/miniforge3/envs/pypsa-rsa/bin/python notebooks/REF-LC_key_figures/make_figures.py
"""
import logging
import os
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

OUT = os.path.dirname(os.path.abspath(__file__))
RUNS = {
    "Original": "backups/REF-LC_LC-182h_pre-correction_2026-10-22/results/Coal_Flexibilisation/REF-LC/LC-182h",
    "Corrected": "results/Coal_Flexibilisation/REF-LC/LC-182h",
}
RM_XLSX = "scenarios/Coal_Flexibilisation/sub_scenarios/reserve_margin.xlsx"  # read-only
RM_LABEL, CC_LABEL = "RES_MRGN_10", "BASE2"
H2 = ["ocgt_gas_h2_40", "ocgt_gas_h2_45", "ocgt_gas_h2_50", "ocgt_gas_h2_55", "ocgt_gas_h2_60"]
SOLAR = ["solar_pv", "solar_pv_low", "solar_pv_rooftop"]

# Reference palette (dataviz skill), default categorical order; stack order = slot order
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
MIX = {  # category -> colour, bottom to top
    "Coal (operational)": "#2a78d6",
    "Nuclear": "#eb6834",
    "Gas OCGT": "#1baf7a",
    "H₂-ready OCGT": "#eda100",
    "Diesel OCGT": "#e87ba4",
    "CCGT steam": "#008300",
    "Solar PV": "#6250d6",
    "Other": "#b5b3ad",
}
RUN_SHADE = {"Original": "#b5b3ad", "Corrected": INK2}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
    "legend.frameon": False, "savefig.dpi": 200,
})


def active_cap(n, c, y, idx):
    df = n.df(c)
    act = n.get_active_assets(c, y).reindex(idx).fillna(False)
    cap = df.loc[idx, "p_nom_opt"].where(df.loc[idx, "p_nom_extendable"], df.loc[idx, "p_nom"])
    return cap.where(act, 0.0)


def load_run(base):
    n = pypsa.Network(f"{base}/networks/solved.nc")
    dec = pd.read_csv(f"{base}/outputs/decom_status.csv", index_col=0).iloc[:, 0]
    g, P = n.generators, n.investment_periods
    coal = g.index[(g.carrier == "coal") & ~g.p_nom_extendable]
    endo = [y for y in P if y >= 2030]  # config: endogenous_decomssioning_start_year

    def ret_frac(gen, y):
        return sum(dec.get(f"{gen}_{yy}", 0.0) for yy in endo if yy <= y)

    r = {"n": n, "P": P}
    # Coal: cumulative endogenous retirement (all stations) vs remaining operational capacity
    r["coal_ceiling"] = pd.Series({y: active_cap(n, "Generator", y, coal).sum() for y in P})
    r["coal_ret_cum"] = pd.Series({y: sum(g.at[c_, "p_nom"] * ret_frac(c_, y) for c_ in coal) for y in P})
    r["coal_ret_active"] = pd.Series({
        y: sum(g.at[c_, "p_nom"] * ret_frac(c_, y) for c_ in coal[active_cap(n, "Generator", y, coal) > 0]) for y in P})
    r["coal_oper"] = r["coal_ceiling"] - r["coal_ret_active"]

    # New build (extendable) active capacity by group
    ext = g[g.p_nom_extendable]
    groups = {"Gas OCGT": ["ocgt_gas"], "H₂-ready OCGT": H2, "Diesel OCGT": ["ocgt_diesel"], "CCGT steam": ["ccgt_steam"]}
    r["new"] = pd.DataFrame({k: {y: active_cap(n, "Generator", y, ext.index[ext.carrier.isin(v)]).sum() for y in P}
                             for k, v in groups.items()})

    # Installed mix (existing + new); coal net of endogenous retirement
    mix = {}
    for y in P:
        cap = active_cap(n, "Generator", y, g.index).groupby(g.carrier).sum().drop("load_shedding", errors="ignore")
        su = active_cap(n, "StorageUnit", y, n.storage_units.index).sum()
        row = {
            "Coal (operational)": r["coal_oper"][y],
            "Nuclear": cap.get("nuclear", 0),
            "Gas OCGT": cap.get("ocgt_gas", 0),
            "H₂-ready OCGT": cap.reindex(H2).fillna(0).sum(),
            "Diesel OCGT": cap.get("ocgt_diesel", 0),
            "CCGT steam": cap.get("ccgt_steam", 0),
            "Solar PV": cap.reindex(SOLAR).fillna(0).sum(),
        }
        named = ["coal", "nuclear", "ocgt_gas", "ocgt_diesel", "ccgt_steam"] + H2 + SOLAR
        row["Other"] = cap.drop(named, errors="ignore").sum() + su
        mix[y] = row
    r["mix"] = pd.DataFrame(mix).T

    # Reserve margin, recomputed ex post (custom_constraints.reserve_margin_constraints)
    rm = pd.read_excel(RM_XLSX, sheet_name="reserve_margin", index_col=[0, 1]).loc[RM_LABEL].drop("units", axis=1)
    cc = pd.read_excel(RM_XLSX, sheet_name="capacity_credits", index_col=0)[CC_LABEL]
    peak = n.loads_t.p_set.sum(axis=1).groupby(level=0).max()
    rows = {}
    for y in P:
        firm = 0.0
        for c in ["Generator", "StorageUnit"]:
            df = n.df(c)
            i = df.index[df.carrier.isin(cc.index)]
            firm += (df.loc[i, "carrier"].map(cc) * active_cap(n, c, y, i)).sum()
        req = peak[y] * (1 + rm.loc["reserve_margin", y])
        net = firm - cc["coal"] * r["coal_ret_active"][y]
        rows[y] = {"active": bool(rm.loc["reserve_margin_active", y]), "requirement": req, "net_firm": net, "slack": net - req}
    r["rm"] = pd.DataFrame(rows).T

    # CO2 (generation x outputs/generator_emissions.csv, kg/MWh; excludes stand-by emissions)
    w = n.snapshot_weightings.generators
    E = n.generators_t.p.mul(w, axis=0).groupby(level=0).sum()
    em = pd.read_csv(f"{base}/outputs/generator_emissions.csv", index_col=0)
    em.index = em.index.astype(int)
    common = E.columns.intersection(em.columns)
    co2 = (E[common] * em.loc[E.index, common]) / 1e9  # Mt
    r["co2_total"] = co2.sum(axis=1)
    r["co2_by_carrier"] = co2.T.groupby(g.loc[common, "carrier"]).sum().T
    r["gen_by_carrier"] = E.T.groupby(g.carrier).sum().T / 1e6  # TWh

    ls = g.index[g.carrier == "load_shedding"]
    r["load_shed_MWh"] = float(E[ls].sum().sum())
    r["objective_bnZAR"] = n.objective / 1e6  # kZAR -> bn ZAR
    return r


def style_axes(ax, ylabel):
    ax.set_ylabel(ylabel)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)


def fig1_mix(R):
    fig, ax = plt.subplots(figsize=(10, 5.6))
    cols = [("2030", "Original"), ("2030", "Corrected"), ("2050", "Original"), ("2050", "Corrected")]
    x = np.array([0, 1, 2.6, 3.6])
    for xi, (yr, run) in zip(x, cols):
        bottom = 0.0
        for cat, colr in MIX.items():
            v = R[run]["mix"].loc[int(yr), cat] / 1e3
            if v <= 0:
                continue
            ax.bar(xi, v, bottom=bottom, width=0.7, color=colr, edgecolor=SURFACE, linewidth=1.5)
            if v >= 6:
                ax.text(xi, bottom + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=9,
                        color="white" if cat not in ("H₂-ready OCGT", "Other", "Diesel OCGT") else INK)
            bottom += v
        ax.text(xi, bottom + 3, f"{bottom:.0f}", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(x, [f"{r}\n{y}" for y, r in cols])
    style_axes(ax, "Installed capacity (GW)")
    ax.set_title("Installed capacity mix, 2030 and 2050", loc="left", fontsize=14)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in MIX.values()]
    ax.legend(handles[::-1], list(MIX)[::-1], loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=10)
    fig.text(0.01, 0.01, "Coal net of endogenous retirement. Other = wind, hydro, hydro imports, CSP, bioenergy, Sasol, "
             "RMIPPP, storage. Labels in GW.", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(f"{OUT}/fig1_capacity_mix_2030_2050.png")
    plt.close(fig)


def fig2_ocgt(R):
    fig, ax = plt.subplots(figsize=(10, 5.6))
    yrs = [2030, 2035, 2040, 2045, 2050]
    ends = []
    for cat in ["Gas OCGT", "H₂-ready OCGT", "Diesel OCGT"]:
        for run, ls in [("Original", "--"), ("Corrected", "-")]:
            s = R[run]["new"].loc[yrs, cat] / 1e3
            ax.plot(yrs, s, ls, color=MIX[cat], linewidth=2, marker="o", markersize=6,
                    markeredgecolor=SURFACE, markeredgewidth=1.5)
            ends.append([s.iloc[-1], f"{cat} – {run.lower()}  {s.iloc[-1]:.1f}"])
    # spread end labels so none overlap (min 1.1 GW apart)
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 1.1)
    for y, txt in ends:
        ax.annotate(txt, (2050, y), xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=9, color=INK2, annotation_clip=False)
    ax.set_xticks(yrs)
    ax.set_xlim(2029, 2050.5)
    style_axes(ax, "New-build capacity in operation (GW)")
    ax.set_title("New OCGT capacity by fuel type, 2030–2050", loc="left", fontsize=14)
    ax.plot([], [], "-", color=INK2, label="Corrected (22 Oct)")
    ax.plot([], [], "--", color=INK2, label="Original (6 Oct)")
    ax.legend(loc="upper left")
    fig.text(0.01, 0.01, "Excludes existing diesel OCGT fleet and CCGT steam. Gas / H₂-ready / diesel split is not "
             "unique (identical costs; see caveats).", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 0.80, 1))
    fig.savefig(f"{OUT}/fig2_ocgt_trajectories.png")
    plt.close(fig)


def fig3_coal(R):
    fig, ax = plt.subplots(figsize=(10, 5.6))
    P = list(R["Corrected"]["P"])
    ceil_ = R["Corrected"]["coal_ceiling"] / 1e3
    ax.step(P, ceil_, where="post", color=MUTED, linewidth=1.5, linestyle=":")
    ax.annotate("Within technical lifetime (scheduled)", (2040, ceil_[2040]), xytext=(0, 8),
                textcoords="offset points", ha="center", fontsize=9, color=MUTED)
    for run, ls in [("Original", "--"), ("Corrected", "-")]:
        s = R[run]["coal_oper"] / 1e3
        ax.step(P, s, ls, where="post", color=MIX["Coal (operational)"], linewidth=2,
                label=f"{run} — operational (net of endogenous retirement)")
        ax.plot(P, s, "o", color=MIX["Coal (operational)"], markersize=6, markeredgecolor=SURFACE,
                markeredgewidth=1.5)
    for run, dy in [("Original", -14), ("Corrected", 8)]:
        v = R[run]["coal_oper"][2030] / 1e3
        ax.annotate(f"{run}: {v:.1f} GW", (2032.5, v), xytext=(0, dy), textcoords="offset points",
                    ha="center", fontsize=9, color=INK2)
    ax.annotate("41.4 GW", (P[0], R["Corrected"]["coal_oper"][P[0]] / 1e3), xytext=(8, 6),
                textcoords="offset points", fontsize=9, color=INK2)
    ax.set_xticks(P)
    style_axes(ax, "Coal capacity (GW)")
    ax.set_title("Operational coal capacity after scheduled and endogenous retirement", loc="left", fontsize=14)
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.85), handlelength=3)
    fig.text(0.01, 0.01, "Each value applies to the whole 5-year investment period (step). Dotted: stations within "
             "their scheduled technical lifetime.", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(f"{OUT}/fig3_coal_remaining.png")
    plt.close(fig)


def fig4_rm(R):
    fig, ax = plt.subplots(figsize=(10, 5.6))
    yrs = [2030, 2035, 2040, 2045, 2050]
    x = np.arange(len(yrs))
    for k, run in enumerate(["Original", "Corrected"]):
        v = R[run]["rm"].loc[yrs, "net_firm"] / 1e3
        ax.bar(x + (k - 0.5) * 0.36, v, width=0.34, color=RUN_SHADE[run], edgecolor=SURFACE, linewidth=1.5,
               label=f"{run} — firm capacity net of retired coal")
    req = R["Corrected"]["rm"].loc[yrs, "requirement"] / 1e3
    for xi, rq in zip(x, req):
        ax.plot([xi - 0.42, xi + 0.42], [rq, rq], color=INK, linewidth=2)
    ax.plot([], [], color=INK, linewidth=2, label="Requirement (peak × 1.10)")
    for xi, y in zip(x, yrs):
        s = R["Original"]["rm"].loc[y, "slack"] / 1e3
        ax.annotate(f"{s:.1f}", (xi - 0.18, R["Original"]["rm"].loc[y, "net_firm"] / 1e3), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=9, color=INK2)
    ax.set_xticks(x, yrs)
    style_axes(ax, "Credited firm capacity (GW)")
    ax.set_title("Reserve-margin compliance before and after correction", loc="left", fontsize=14)
    ax.legend(loc="upper left")
    fig.text(0.01, 0.01, "Recomputed with BASE2 capacity credits. Labels: original shortfall (GW). "
             "Corrected run meets the requirement in every period (slack < 0.1 MW).", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(f"{OUT}/fig4_reserve_margin.png")
    plt.close(fig)


def main():
    R = {k: load_run(v) for k, v in RUNS.items()}
    pd.set_option("display.width", 200)
    for k, r in R.items():
        print(f"\n===== {k}")
        print(f"objective: {r['objective_bnZAR']:.1f} bn ZAR (PV) | load shedding: {r['load_shed_MWh']:.2e} MWh")
        print("new-build active (GW):\n", (r["new"] / 1e3).round(2).T.to_string())
        print("coal (GW): ceiling / cumulative endogenous retired / operational\n",
              pd.DataFrame({"ceiling": r["coal_ceiling"], "ret_cum": r["coal_ret_cum"], "operational": r["coal_oper"]})
              .div(1e3).round(2).T.to_string())
        print("reserve margin (GW):\n", r["rm"][["requirement", "net_firm", "slack"]].astype(float).div(1e3).round(3).T.to_string())
        print("installed mix (GW):\n", (r["mix"] / 1e3).round(1).T.to_string())
        print("CO2 total (Mt):", r["co2_total"].round(2).to_dict())
    d = (R["Corrected"]["co2_by_carrier"].loc[2030] - R["Original"]["co2_by_carrier"].reindex(columns=R["Corrected"]["co2_by_carrier"].columns, fill_value=0).loc[2030])
    print("\n2030 CO2 by carrier (Mt): original / corrected / delta")
    t = pd.DataFrame({"original": R["Original"]["co2_by_carrier"].loc[2030], "corrected": R["Corrected"]["co2_by_carrier"].loc[2030]}).fillna(0)
    t["delta"] = t.corrected - t.original
    print(t[t.abs().max(axis=1) > 0.05].round(2).to_string())
    gt = pd.DataFrame({"original": R["Original"]["gen_by_carrier"].loc[2030], "corrected": R["Corrected"]["gen_by_carrier"].loc[2030]}).fillna(0)
    gt["delta"] = gt.corrected - gt.original
    print("\n2030 generation by carrier (TWh):\n", gt[gt.abs().max(axis=1) > 0.05].round(2).to_string())
    fig1_mix(R)
    fig2_ocgt(R)
    fig3_coal(R)
    fig4_rm(R)
    print("\nfigures written to", OUT)


if __name__ == "__main__":
    main()
