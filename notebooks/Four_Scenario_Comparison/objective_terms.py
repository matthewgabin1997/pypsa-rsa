"""Load a solved scenario and rebuild its optimisation objective term by term (read-only).

Extracted verbatim from the verified cost-reconciliation script (costrec/reconcile.py, 27 Oct 2026), which reproduces
n.objective exactly (residual 0) for REF-LC, POL-3GW, POL-6GW and POL-18.25GW. Only the repository path handling changed.

Objective (PyPSA 0.35.2 define_objective + prepare_and_solve_network.add_coal_decom), all in kZAR
(scale_costs(n, 1e3) divided every *cost* attribute by 1000 before the solve; solved.nc keeps the scaled values):
  T1  capex of extendable assets      sum_c sum_i capital_cost_i * p_nom_opt_i * sum_{periods y where i active} w_obj[y]
  T2  marginal / storage / spill      sum_t w_obj[period(t)] * w_snap_obj[t] * cost_i(t) * dispatch_i(t)
  T3  stand-by (committable gens)     sum_t w_obj * w_snap * stand_by_cost * status
  T4  start-up / shut-down            sum_t start_up_cost * start_up  (NOT period- or snapshot-weighted)
  T5  coal retirement (variable)      - sum_y sum_{gen active in y} FOM_gen * w_obj[y] * p_nom_gen * cumret_gen(y)
  T6  coal retirement (constant)      - sum_y sum_{gen active in y} FOM_gen * w_obj[y] * p_nom_gen * min_phased(y, gen)
  T0  PyPSA constant (existing p_nom of extendables) - 0 here
  n.objective = m.objective.value = T1 + T2 + T3 + T4 + T5 + T6 (+ T0)
"""
import os

import pandas as pd
import pypsa

# repository root = two levels above this file (notebooks/Four_Scenario_Comparison/)
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")) + os.sep
SCHED = pd.read_excel(REPO + "scenarios/Coal_Flexibilisation/sub_scenarios/phased_decommissioning.xlsx",
                      sheet_name="schedule", index_col=[0, 1]).loc["DELAYED_ESKOM_2035"].round(2)


def load(s):
    d = REPO + f"results/Coal_Flexibilisation/{s}/LC-182h/"
    n = pypsa.Network(d + "networks/solved.nc")
    ret = pd.read_csv(d + "outputs/decom_status.csv", index_col=0).iloc[:, 0]
    return n, ret


def terms(n, ret):
    periods = list(n.investment_periods)
    wy = n.investment_period_weightings["objective"]
    wt = n.snapshot_weightings["objective"].mul(wy, level=0)  # per-snapshot objective weight
    T = {}
    per = {}  # per-period breakdown (PV) for T1-T6

    # T1 capex of extendables
    t1, t1p = 0.0, pd.Series(0.0, index=periods)
    for c in ("Generator", "StorageUnit", "Link", "Store", "Line"):
        df = n.static(c) if hasattr(n, "static") else n.df(c)
        if df.empty or "capital_cost" not in df:
            continue
        attr = {"Generator": "p_nom", "StorageUnit": "p_nom", "Link": "p_nom", "Store": "e_nom", "Line": "s_nom"}[c]
        ext = df[df[f"{attr}_extendable"]] if f"{attr}_extendable" in df else df.iloc[0:0]
        for y in periods:
            act = n.get_active_assets(c, y)[ext.index]
            v = (ext.capital_cost * ext[f"{attr}_opt"])[act].sum() * wy[y]
            t1p[y] += v
            t1 += v
    T["T1 capex (extendable, annuity incl. FOM)"] = t1
    per["T1"] = t1p

    # T2 marginal / storage / spill
    t2p = pd.Series(0.0, index=periods)
    for c, cost, var in (("Generator", "marginal_cost", "p"), ("StorageUnit", "marginal_cost", "p_dispatch"),
                         ("StorageUnit", "marginal_cost_storage", "state_of_charge"), ("StorageUnit", "spill_cost", "spill"),
                         ("Link", "marginal_cost", "p0"), ("Store", "marginal_cost", "p")):
        df = n.df(c)
        if df.empty or cost not in df:
            continue
        mc = n.get_switchable_as_dense(c, cost)
        x = n.pnl(c).get(var)
        if x is None or x.empty:
            continue
        cols = mc.columns.intersection(x.columns)
        v = (mc[cols] * x[cols]).sum(axis=1) * wt
        t2p += v.groupby(level=0).sum()
    T["T2 marginal cost (fuel, VOM, carbon tax)"] = t2p.sum()
    per["T2"] = t2p

    # T3 stand-by, T4 start-up / shut-down
    com = n.generators.index[n.generators.committable]
    t3p = pd.Series(0.0, index=periods)
    if len(com):
        sb = n.get_switchable_as_dense("Generator", "stand_by_cost")[com]
        st = n.generators_t.status.reindex(columns=com).fillna(0)
        t3p = ((sb * st).sum(axis=1) * wt).groupby(level=0).sum()
    T["T3 stand-by cost (committable coal)"] = t3p.sum()
    per["T3"] = t3p
    t4 = 0.0
    t4p = pd.Series(0.0, index=periods)
    for a in ("start_up", "shut_down"):
        cost = n.generators.loc[com, f"{a}_cost"]
        x = n.generators_t.get(a, pd.DataFrame()).reindex(columns=com).fillna(0)
        if not x.empty and cost.abs().sum():
            v = (x * cost).sum(axis=1)
            t4p += v.groupby(level=0).sum()
            t4 += v.sum()
    T["T4 start-up / shut-down (unweighted)"] = t4
    per["T4"] = t4p

    # T5 / T6 coal retirement
    coal = n.generators[(n.generators.carrier == "coal") & ~n.generators.p_nom_extendable]
    decom_periods = [y for y in periods if y >= 2030]
    t5p, t6p = pd.Series(0.0, index=periods), pd.Series(0.0, index=periods)
    for y in periods:
        act = n.get_active_assets("Generator", y)
        for g in coal.index[act[coal.index]]:
            fom, pn = coal.at[g, "capital_cost"], coal.at[g, "p_nom"]
            cum = sum(ret.get(f"{g}_{yy}", 0.0) for yy in decom_periods if yy <= y)
            t5p[y] += -fom * wy[y] * pn * cum
            t6p[y] += -fom * wy[y] * pn * float(SCHED.loc[y, g]) if g in SCHED.columns else 0.0
    T["T5 coal retirement FOM saving (variable)"] = t5p.sum()
    T["T6 coal retirement constant (sign as coded)"] = t6p.sum()
    per["T5"], per["T6"] = t5p, t6p
    T["sum T1..T6"] = sum(v for k, v in T.items())
    T["n.objective (solved.nc)"] = n.objective
    T["residual (n.objective - sum)"] = n.objective - T["sum T1..T6"]
    return pd.Series(T), pd.DataFrame(per)
