import logging
import pandas as pd
import pypsa
from pypsa.descriptors import get_switchable_as_dense as get_as_dense, expand_series, get_activity_mask
from pypsa.optimization.common import reindex
import os

from _helpers import get_investment_periods
# from add_electricity import load_costs, update_transmission_costs

import xarray as xr
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning) # Comment out for debugging and development

idx = pd.IndexSlice
logger = logging.getLogger(__name__)


"""
********************************************************************************
    Operational limits
********************************************************************************
"""

def calc_max_gen_potential(n, sns, gens, incl_pu, weightings, active, cf_limit, extendable=False):
    suffix = "" if extendable == False else "-ext"
    p_max_pu = get_as_dense(n, 'Generator', "p_max_pu", sns)[gens] if incl_pu else pd.DataFrame(1, index=sns, columns=gens)
    p_max_pu.columns.name = f'Generator{suffix}'
    
    if n.multi_invest:
        cf_limit_h = pd.DataFrame(0, index=sns, columns=gens)
        for y in cf_limit_h.index.get_level_values(0).unique():
            cf_limit_h.loc[y] = cf_limit[y]
    else:
        cf_limit_h = pd.DataFrame(cf_limit[sns[0].year], index=sns, columns=gens) * weightings[gens]
    
    if not extendable:
        return (cf_limit_h[gens] * active[gens] * p_max_pu * weightings[gens] * n.generators.loc[gens, "p_nom"]).sum(axis=1)
    p_nom = n.model.variables["Generator-p_nom"].sel({f"Generator{suffix}": gens})
    potential = xr.DataArray(cf_limit_h[gens] * active[gens] * p_max_pu * weightings[gens])
    potential = potential.rename({"Generator":"Generator-ext"}) if "Generator" in potential.dims else potential
    
    return (potential * p_nom).sum(f'Generator{suffix}')

def group_and_sum(data, groupby_func):
    grouped_data = data.groupby(groupby_func).sum()
    return grouped_data.sum(axis=1) if len(grouped_data) > 1 else grouped_data
    
def apply_operational_constraints(n, sns, **kwargs):
    energy_unit_conversion = {"GW":1e3, "GJ": 1/3.6, "TJ": 1000/3.6, "PJ": 1e6/3.6, "GWh": 1e3, "TWh": 1e6}
    apply_to = kwargs["apply_to"]

    carrier = [c.strip() for c in kwargs["carrier"].split("+")]
    bus = kwargs["bus"]
    period = kwargs["period"]
    type_ = "energy_power" if kwargs["type"] in ["primary_energy", "output_energy", "output_power"] else "capacity_factor"

    if (period  == "week") & (max(n.snapshot_weightings["generators"])>1):
        logger.warning(
            "Applying weekly operational limits and time segmentation should be used with caution as the snapshot weightings might not align with the weekly grouping."
        )
    incl_pu = kwargs["incl_pu"]
    limit = kwargs["limit"]

    sense = "<=" if limit == "max" else ">="

    if len(sns) <8760 and not n.multi_invest and period in ["week", "month"]: #conditions for rolling horizon analysis monthly
        sns = sns[sns.month == sns.month[0]] # ignore overlap with next month for monthly limits

    cf_limit = 0 * kwargs["values"] if type_ == "energy_power" else kwargs["values"]
    en_pow_limit = 0 * kwargs["values"] if type_ == "capacity_factor" else kwargs["values"]

    if ((kwargs["type"] in ["primary_energy", "output_energy"]) & (kwargs["units"] != "MWh")) or ((kwargs["type"] == "output_power") & (kwargs["units"] != "MW")):
        en_pow_limit *= energy_unit_conversion[kwargs["units"]]

    years = get_investment_periods(sns, n.multi_invest)

    filtered_gens = n.generators.query("carrier in @carrier") if len(carrier)>1 else n.generators.query("carrier == @carrier")
    if bus != "global":
        filtered_gens = filtered_gens.query("bus == @bus")
    fix_i = filtered_gens.query("not p_nom_extendable").index if apply_to in ["fixed", "all"] else []
    ext_i = filtered_gens.query("p_nom_extendable").index if apply_to in ["extendable", "all"] else []
    filtered_gens = filtered_gens.loc[list(fix_i) + list(ext_i)]

    if len(filtered_gens) == 0:
        return

    efficiency = get_as_dense(n, "Generator", "efficiency", inds=filtered_gens.index) if kwargs["type"] == "primary_energy" else pd.DataFrame(1, index=n.snapshots, columns = filtered_gens.index)
    weightings = (1/efficiency).multiply(n.snapshot_weightings.generators, axis=0)

    # if only extendable generators only select snapshots where generators are active
    min_year = n.generators.loc[filtered_gens.index, "build_year"].min()
    sns_active = sns[sns.get_level_values(0) >= min_year] if n.multi_invest else sns[sns.year >= min_year]
    act_gen = (n.model.variables['Generator-p'].loc[sns_active, filtered_gens.index] * weightings.loc[sns_active]).sel(Generator=filtered_gens.index).sum('Generator')
    act_gen_pow = (n.model.variables['Generator-p'].loc[sns_active, filtered_gens.index]).sel(Generator=filtered_gens.index).sum('Generator')

    timestep = "timestep" if n.multi_invest else "snapshot"
    groupby_dict = {
        "year": f"{timestep}.year",
        "month": f"{timestep}.month",
        "week": f"{timestep}.week",
        "hour": None
    }

    active = get_activity_mask(n, "Generator", sns).astype(int)
    if type_ != "energy_power":
        max_gen_fix = calc_max_gen_potential(n, sns, fix_i, incl_pu, weightings, active, cf_limit, extendable=False) if len(fix_i)>0 else 0
        max_gen_ext = calc_max_gen_potential(n, sns, ext_i, incl_pu, weightings, active, cf_limit, extendable=True) if len(ext_i)>0 else 0

    if groupby := groupby_dict[period]:
        for y in years:
            year_sns = sns_active[sns_active.get_level_values(0)==y] if n.multi_invest else sns_active
            if len(year_sns) > 0:
                if type_ == "capacity_factor":
                    lhs = (act_gen - max_gen_ext) 
                    if isinstance(max_gen_fix, (int, float)):
                        rhs = max_gen_fix
                        skip_constraint = 0 if rhs >=0 else 1
                    else:
                        rhs = max_gen_fix.loc[y] if n.multi_invest else max_gen_fix.loc[year_sns]
                        skip_constraint = 0 if (rhs >=0).any().any() else 1
                else:
                    lhs = act_gen
                    rhs = en_pow_limit[y]
                    skip_constraint = 0 if rhs >0 else 1 
                if not skip_constraint:
                    lhs = lhs.sel(snapshot=year_sns)
                    lhs_p = lhs.sum() if period == "year" else lhs.groupby(groupby).sum()
                    rhs_p = (
                        rhs
                        if isinstance(rhs, (int, float))
                        else xr.DataArray(rhs).groupby(groupby).sum()
                    )
                    n.model.add_constraints(lhs_p, sense, rhs_p, name=f'{limit}-{kwargs["carrier"]}-{period}-{kwargs["apply_to"][:3]}-{y}')

    else:

        lhs = (act_gen - max_gen_ext).sel(snapshot = sns_active) if type_ == "capacity_factor" else act_gen_pow.sel(snapshot = sns_active)
        if kwargs["type"] == "output_energy":
            logging.warning("Energy limits are not yet implemented for hourly operational limits.")
            return

        if type_ == "capacity_factor":
            if isinstance(max_gen_fix, int):
                rhs = max_gen_fix
            else:
                rhs = xr.DataArray(max_gen_fix.loc[sns_active])
                rhs = rhs.rename({"dim_0": "snapshot"}) if rhs.dims[0] == "dim_0" else rhs # in the case of index name not being snapshot

        else:
            rhs = pd.Series(index = sns)
            if n.multi_invest:
                for y in years:
                    rhs.loc[y] = en_pow_limit[y]
            else:
                rhs.loc[str(years[0])] = en_pow_limit[years[0]]

        n.model.add_constraints(lhs, sense, rhs, name = f'{limit}-{kwargs["carrier"]}-hour-{kwargs["apply_to"][:3]}')

# MG added: gas-utilisation floor indexed to policy-mandated gas-turbine capacity (gas-to-power study)
MANDATE_CF_CONTRACT_YEARS = 20  # research assumption informed by South African gas procurement / PPA practice, not a universal contract term
MANDATE_CF_TYPE = "mandate_capacity_factor"  # value in the `capacity_factor` (type) column of operational_constraints.xlsx

def _mandate_cf_value(values, y):
    # MG added: read the floor for investment period y from a workbook row (year columns may be int or str)
    for key in (y, str(y)):
        if key in values.index:
            v = values[key]
            return None if pd.isna(v) else float(v)
    return None

def apply_mandate_cf_floor(n, sns, carrier, bus, values, period, incl_pu, limit, apply_to, units, label=""):
    """
    MG added. Fleet-level minimum natural-gas generation obligation indexed to policy-mandated
    gas-turbine capacity. This is a minimum-generation requirement, not a financially explicit
    take-or-pay agreement.

    For each investment period y and each month (period == "month") or the whole year
    (period == "year"):

        sum_t w_t * sum_{g in G} p_{g,t}  >=  f_y * sum_t w_t * sum_{g in M_y} p_nom_min_g * p_max_pu_{g,t}

    - G   : extendable generators of `carrier` (e.g. ocgt_gas, all vintages). Their aggregate
            dispatch can meet the obligation; generation is not assigned to individual mandated MW.
    - M_y : "mandated" vintages, i.e. members of G with p_nom_min > 0 (set by the
            extendable_min_annual label), active in y and within the contract window
            build_year <= y < build_year + MANDATE_CF_CONTRACT_YEARS. Endogenous capacity above
            p_nom_min does not enter the right-hand side, so it carries no obligation of its own.
    - f_y : floor as a fraction (0-1) taken from the workbook column for year y.
    - p_max_pu is applied if incl_pu is True (available-capacity basis); otherwise nameplate.
    - w_t : n.snapshot_weightings.generators (hours represented by each snapshot); months are the
            actual calendar months of the snapshot timesteps.

    With a 2030 vintage and a 20-year contract, the floor is active in the 2030, 2035, 2040 and 2045
    periods (calendar years 2030-2049) and inactive in 2050, whatever the workbook values are.
    The constraint is added only for rows whose type is MANDATE_CF_TYPE, so all other
    operational-limit configurations (e.g. NO_GAS_FLOOR, NO_MIN_GAS) are unaffected.
    """
    carriers = [c.strip() for c in carrier.split("+")]
    if "ccgt_steam" in carriers:
        raise ValueError("Mandate CF floor must not be applied to ccgt_steam (no independent steam utilisation floor).")
    if limit != "min":
        raise ValueError(f"Mandate CF floor supports limit='min' only, got '{limit}'.")
    if apply_to != "extendable":
        raise ValueError(f"Mandate CF floor supports apply_to='extendable' only, got '{apply_to}'.")
    if period not in ["month", "year"]:
        raise ValueError(f"Mandate CF floor supports period 'month' or 'year' only, got '{period}'.")
    if not n.multi_invest:
        raise ValueError("Mandate CF floor is implemented for multi-period investment networks only.")
    if units not in ["%", "pu", "fraction"]:
        raise ValueError(f"Mandate CF floor values must be fractions (units '%', 'pu' or 'fraction'), got '{units}'.")
    incl_pu = incl_pu if isinstance(incl_pu, bool) else str(incl_pu).strip().lower() in ["true", "1", "1.0"]

    floors = {y: _mandate_cf_value(values, y) for y in n.investment_periods}
    for y, f in floors.items():
        if f is not None and (f < 0 or f > 1):
            raise ValueError(f"Mandate CF floor ({label}, {carrier}) for {y} is {f}; values must be fractions between 0 and 1.")
    positive = [y for y, f in floors.items() if f is not None and f > 0]
    if not positive:
        logger.info(f"Mandate CF floor ({label}, {carrier}): no positive floor in any investment period, nothing added.")
        return

    gens = n.generators.query("carrier in @carriers & p_nom_extendable")
    if bus != "global":
        gens = gens.query("bus == @bus")
    mandated = gens.index[gens["p_nom_min"] > 0]
    if len(mandated) == 0:
        raise ValueError(
            f"Mandate CF floor ({label}, {carrier}): positive floor requested for {positive} but no extendable "
            f"'{carrier}' generator with p_nom_min > 0 (mandated capacity) was found. Check extendable_min_annual."
        )

    p_nom_min = n.generators.loc[mandated, "p_nom_min"]
    build_year = n.generators.loc[mandated, "build_year"]
    p_max_pu = get_as_dense(n, "Generator", "p_max_pu", sns)[mandated] if incl_pu else pd.DataFrame(1.0, index=sns, columns=mandated)
    w = n.snapshot_weightings.generators.loc[sns]
    p = n.model.variables["Generator-p"]

    for y in positive:
        f = floors[y]
        sns_y = sns[sns.get_level_values(0) == y]
        if len(sns_y) == 0:
            continue

        active = n.get_active_assets("Generator", y).reindex(mandated).fillna(False).astype(bool)
        if not active.any():
            raise ValueError(
                f"Mandate CF floor ({label}, {carrier}): positive floor {f} requested for {y} but no mandated "
                f"'{carrier}' capacity is active in that period."
            )
        in_contract = (build_year <= y) & (y < build_year + MANDATE_CF_CONTRACT_YEARS)
        m_y = mandated[active & in_contract]
        if len(m_y) == 0:
            logger.info(
                f"Mandate CF floor ({label}, {carrier}) {y}: outside the {MANDATE_CF_CONTRACT_YEARS}-year contract "
                f"window of all mandated vintages, no floor added."
            )
            continue

        # required generation per snapshot [MWh]: f * w_t * sum_g p_nom_min_g * p_max_pu_g,t
        rhs_t = f * p_max_pu.loc[sns_y, m_y].mul(p_nom_min[m_y], axis=1).sum(axis=1).mul(w.loc[sns_y])
        # weighted aggregate dispatch of all extendable units of the carrier [MWh]
        w_df = pd.DataFrame(1.0, index=sns_y, columns=gens.index).mul(w.loc[sns_y], axis=0)
        w_df.index.name, w_df.columns.name = "snapshot", "Generator"

        groups = sns_y.get_level_values(1).month if period == "month" else [y] * len(sns_y)
        for grp in pd.unique(groups):
            sns_g = sns_y[groups == grp] if period == "month" else sns_y
            rhs = float(rhs_t.loc[sns_g].sum())
            if rhs <= 0:
                continue
            lhs = (p.loc[sns_g, gens.index] * w_df.loc[sns_g]).sum()
            suffix = f"{y}-{int(grp):02d}" if period == "month" else f"{y}"
            n.model.add_constraints(lhs, ">=", rhs, name=f"mandate_cf_floor-{carrier}-{period}-{suffix}")

        logger.info(
            f"Mandate CF floor ({label}, {carrier}, {period}) {y}: f={f:.2f}, mandated MW={p_nom_min[m_y].sum():.0f}, "
            f"required {rhs_t.sum()/1e6:.3f} TWh/yr (incl_pu={incl_pu})."
        )

def set_operational_limits(n, sns, scenario_setup, snakemake, exclude_flag=[]):

    op_limits = pd.read_excel(
        os.path.join(scenario_setup["sub_path"], "operational_constraints.xlsx"),
        sheet_name='operational_constraints',
        index_col=list(range(9)),
    )

    if scenario_setup["operational_limits"] not in op_limits.index.get_level_values(0).unique():
        logging.warning(f"Operational limits for scenario {scenario_setup['operational_limits']} not found, skipping.")
        return
    op_limits = op_limits.loc[scenario_setup["operational_limits"]]

    if len(exclude_flag) > 0:
        logging.warning(f"Excluding operational limits that are specified in {exclude_flag}.")
        op_limits = op_limits.loc[~op_limits.index.get_level_values(3).str.contains("|".join(exclude_flag))]

    #drop rows where all NaN
    op_limits = op_limits.loc[~(op_limits.isna().all(axis=1))]
    for idx, row in op_limits.iterrows():
        if idx[2] == MANDATE_CF_TYPE:  # MG added: route mandate floors to their own function; all other rows unchanged
            apply_mandate_cf_floor(
                n, sns,
                carrier = idx[1], bus = idx[0],
                values = row, period = idx[3], incl_pu = idx[4],
                limit = idx[5], apply_to = idx[6], units = idx[7],
                label = scenario_setup["operational_limits"],
            )
            continue
        apply_operational_constraints(
            n, sns, 
            bus = idx[0], carrier = idx[1], 
            type = idx[2], values = row, 
            period = idx[3], incl_pu = idx[4],
            limit = idx[5], apply_to = idx[6],
            units = idx[7],
        )

def ccgt_steam_constraints(n, sns, scenario_setup, snakemake):
    # At each bus HRSG power is limited by what OCGT power production at that bus
    config = snakemake.config["electricity"]["conventional_generators"]
    p_nom_ratio = config["ccgt_st_to_gt_ratio"]

    ocgt_carriers = pd.read_excel(
            os.path.join(scenario_setup["sub_path"], "aux_stg_feed.xlsx"), 
            sheet_name='allowable_carriers',
            index_col=[0,1,2],
    ).loc[scenario_setup["aux_stg_feed"]]

    years = n.investment_periods if n.multi_invest else [n.snapshots[0].year]
    
    for bus in n.buses.index:
        for y in years:

            carriers = ocgt_carriers[y]
            carriers =carriers[carriers==True]
            carriers = carriers.reset_index().set_index("carrier")

            fix_carriers = carriers[(carriers["apply_to"] == "fixed") | (carriers["apply_to"] == "all")].index
            ext_carriers = carriers[(carriers["apply_to"] == "extendable") | (carriers["apply_to"] == "all")].index
            
            fix_ocgt_gens = n.generators.query("bus == bus & carrier in @fix_carriers & p_nom_extendable == 0").index
            ext_ocgt_gens = n.generators.query("bus == bus & carrier in @ext_carriers & p_nom_extendable == 1").index
            ocgt_gens = list(fix_ocgt_gens) + list(ext_ocgt_gens)

            if len(n.investment_periods) > 0:
                sns_y = sns[sns.get_level_values(0)==y]
                ccgt_hrsg = n.generators[n.get_active_assets("Generator",y)].query("bus == bus & carrier == 'ccgt_steam'").index
            else:
                sns_y = sns
                ccgt_hrsg = n.generators.query("bus == bus & carrier == 'ccgt_steam'").index

            if len(ccgt_hrsg) == 0:
                continue
            lhs = (n.model.variables['Generator-p'].loc[sns_y, ccgt_hrsg] - p_nom_ratio*n.model.variables['Generator-p'].loc[sns_y, ocgt_gens]).sum("Generator")
            rhs = 0
            n.model.add_constraints(lhs, "<=", rhs, name = f'ccgt_steam_limit-{bus}-{y}')

"""
********************************************************************************
    Limit number of start-ups for coal plant
********************************************************************************
"""
def limit_coal_start_ups_capacity(n, sns, limit, full_outages_pu_max):

    delta_full_outages_up = full_outages_pu_max.diff().fillna(0)
    delta_full_outages_up[delta_full_outages_up<0] = 0
    delta_full_outages_up = delta_full_outages_up.groupby(level=0).sum()
    delta_full_outages_up.columns.name = "Generator-com" # reindex for Xarray

    # Limit coal plant start-ups
    coal_gens = n.generators.query("carrier == 'coal' & committable").index
    lhs = n.model.variables['Generator-start_up'].sel({"Generator-com":coal_gens}).groupby("period").sum()
    rhs = limit + delta_full_outages_up
    n.model.add_constraints(lhs, "<=", rhs, name = f'coal_startup_limits')

"""
********************************************************************************
    Reserve margin
********************************************************************************
"""
def check_active(n, c, y, list):
    active = n.df(c).index[n.get_active_assets(c, y)] if n.multi_invest else list
    return list.intersection(active)

def reserve_margin_constraints(n, sns, scenario_setup, snakemake):
    ###################################################################################
    # Reserve margin above maximum peak demand in each year
    # The sum of res_margin_carriers multiplied by their assumed constribution factors
    # must be higher than the maximum peak demand in each year by the reserve_margin value

    # AM added: allow reserve_margin = none to skip constraint entirely
    if str(scenario_setup.get("reserve_margin", "none")).strip().lower() in ["none", "0", "false", ""]:
        return

    endogenous_decom_start_year = snakemake.config["electricity"]["conventional_generators"]["endogenous_decomssioning_start_year"]
    decom_periods = n.investment_periods[n.investment_periods >= endogenous_decom_start_year]


    res_margin = pd.read_excel(
        os.path.join(scenario_setup["sub_path"], "reserve_margin.xlsx"), 
        sheet_name="reserve_margin",
        index_col=[0,1]).loc[scenario_setup["reserve_margin"]].drop("units", axis=1)

    capacity_credit = pd.read_excel(
            os.path.join(scenario_setup["sub_path"], "reserve_margin.xlsx"), 
            sheet_name="capacity_credits",
            index_col=[0])[scenario_setup["capacity_credits"]]

    res_mrgn_active = res_margin.loc["reserve_margin_active"]
    res_mrgn = res_margin.loc["reserve_margin"]

    peak = n.loads_t.p_set.loc[sns].sum(axis=1).groupby(sns.get_level_values(0)).max() if n.multi_invest else n.loads_t.p_set.loc[sns].sum(axis=1).max()
    peak = peak if n.multi_invest else pd.Series(peak, index = sns.year.unique())
    #capacity_credit = snakemake.config["electricity"]["reserves"]["capacity_credit"]

    for y in peak.index:
        if res_mrgn_active[y]:    

            fix_i = n.generators.query("not p_nom_extendable & carrier in @capacity_credit").index
            ext_i = n.generators.query("p_nom_extendable & carrier in @capacity_credit").index
    
            fix_cap = 0
            lhs = 0
            for c in ["Generator", "StorageUnit"]:
                fix_i = n.df(c).query("not p_nom_extendable & carrier in @capacity_credit.index").index
                fix_i = check_active(n, c, y, fix_i)

                fix_cap += (
                    n.df(c).loc[fix_i, "carrier"].map(capacity_credit)
                    * n.df(c).loc[fix_i, "p_nom"]
                ).sum()
            
                ext_i = n.df(c).query("p_nom_extendable & carrier in @capacity_credit.index").index
                ext_i = check_active(n, c, y, ext_i)
    
                lhs += (
                    n.model.variables[f"{c}-p_nom"].sel({f"{c}-ext":ext_i}) 
                    *xr.DataArray(n.df(c).loc[ext_i, "carrier"].map(capacity_credit)).rename({f"{c}":f"{c}-ext"})
                ).sum(f"{c}-ext")

            #### Remove decommisioned coal from the reserve margin
            coal_decom = 0
            if scenario_setup["endogenous_coal_decom"]:
                coal_gens = n.generators.query("carrier == 'coal' and not p_nom_extendable").index
                coal_gens = check_active(n, "Generator", y, coal_gens)
                for gen in coal_gens:
                    p_nom = n.generators.loc[gen, "p_nom"]
                    retired_sum= [f"{gen}_{y_it}" for y_it in decom_periods if y_it <= y]    
                    p_nom_retired = n.model.variables["Generator-p_nom_ret"].sel({"Generator-ret":retired_sum}).sum()
                    if len(retired_sum) > 0:
                        coal_decom += capacity_credit.loc["coal"] * p_nom * p_nom_retired

            lhs = lhs - coal_decom  # MG adjusted: `coal_decom != 0` is always False for a linopy expression (== returns a truthy Constraint), so retired coal was never removed
            rhs = peak.loc[y]*(1+res_mrgn[y]) - fix_cap
            n.model.add_constraints(lhs, ">=", rhs, name = f"reserve_margin_{y}")    

def add_annual_co2_constraints(n, sns, scenario_setup, gen_emissions):

    annual_limits = pd.read_excel(
        os.path.join(scenario_setup["sub_path"], "emissions.xlsx"),
        sheet_name="annual_carbon_constraint",
        index_col=[0]).loc[scenario_setup["co2_cap"]]  # AM adjusted: was carbon_constraints, which also holds the unrelated CT_REINVEST flag

    conv = 1
    if annual_limits.unit.split("/")[0] == "Mt":
        conv = 1e9 # convert to kgCO2
    elif annual_limits.units.split("/")[0] == "Gt":
        conv = 1e12 # convert to kgCO2

    gen_p = n.model.variables['Generator-p']
    gen_p = gen_p.sel(Generator = gen_emissions.index)

    for y in n.investment_periods:
        lhs = gen_p.sel(period=y).sum("timestep") * gen_emissions[str(y)]
        rhs = (annual_limits.loc[y] * conv)
        n.model.add_constraints(lhs, "<=", rhs, name = f'annual_carbon_limits_{y}')


# AM added -----------------------------------------------------------------------
def add_ct_reinvestment_constraint(n, sns, SCENARIO_SETUP, snakemake):
    """
    Two-stage CT revenue recycling constraint (Paper 0).

    Reads 2030 emissions from the solved reference scenario (e.g. P0_BASE for
    P0_BASE_R), calculates CT revenues at the official SA 2030 headline rate
    (462 R/tCO2), and enforces a minimum annualised RE investment >= those revenues.

    Must be called after scale_costs(n, 1e3) — capital_cost in n is already
    divided by 1e3, so ct_revenues is scaled by the same factor.
    """
    reinvest_carriers = ['wind', 'wind_low', 'solar_pv', 'solar_pv_low']
    ct_rate = 462  # R/tCO2 — official SA 2030 headline rate

    # Step 1: paths to reference scenario outputs (remove _R suffix)
    # SCENARIO_SETUP is a pandas Series — scenario name is .name, not a key
    base_scenario  = SCENARIO_SETUP.name.replace("_R", "")
    working_folder = snakemake.config["scenarios"]["working_folder"]
    options        = snakemake.wildcards.options
    base_net_path  = os.path.join(
        "results", working_folder, base_scenario, options, "networks", "solved.nc"
    )
    base_emis_path = os.path.join(
        "results", working_folder, base_scenario, options, "outputs", "generator_emissions.csv"
    )

    # Step 2: load reference network and emission factors (pypsa imported at module level)
    n_base = pypsa.Network(base_net_path)
    # gen_emissions: index=period (2025,2030), columns=generator names, values=kgCO2/MWh
    gen_emissions = pd.read_csv(base_emis_path, index_col=0)

    # Step 3: annual generation per generator in 2030 from reference
    # generators_t.p has MultiIndex (period, snapshot) in multi-invest mode
    # AM adjusted: must weight by snapshot_weightings before summing — raw .sum() gives MW not MWh
    #gen_p_annual = n_base.generators_t.p.groupby(level=0).sum()  # AM adjusted: wrong — no weighting
    w            = n_base.snapshot_weightings["generators"]        # MWh weighting per snapshot
    gen_p_annual = n_base.generators_t.p.mul(w, axis=0).groupby(level=0).sum()  # period × generator [MWh]
    gen_p_2030   = gen_p_annual.loc[2030]                         # Series: generator → MWh

    # align generators present in both generation and emission-factor data
    common_gens  = gen_emissions.columns.intersection(gen_p_2030.index)
    ef_2030      = gen_emissions.loc[2030, common_gens]           # kgCO2/MWh

    emissions_kg = (gen_p_2030[common_gens] * ef_2030).sum()      # kgCO2
    emissions_t  = emissions_kg / 1000                             # tCO2

    ct_revenues  = ct_rate * emissions_t                           # R

    logger.info(
        f"CT reinvestment [{SCENARIO_SETUP.name}]: "
        f"{emissions_t/1e6:.2f} MtCO2 × {ct_rate} R/t = {ct_revenues/1e9:.2f} bn ZAR"
    )

    # Step 3.5: baseline RE investment from reference scenario (already in scaled kZAR/MW,
    # because capital_cost is stored post-scale_costs in the solved .nc)
    base_re_gens = n_base.generators.query(
        "carrier in @reinvest_carriers and build_year == 2030 and p_nom_extendable"
    )
    base_re_investment = (base_re_gens.p_nom_opt * base_re_gens.capital_cost).sum()  # kZAR/yr

    logger.info(
        f"CT reinvestment [{SCENARIO_SETUP.name}]: "
        f"base RE investment = {base_re_investment/1e6:.2f} bn kZAR/yr, "
        f"CT revenues = {ct_revenues/1e9:.2f} bn ZAR → "
        f"total RHS = {(base_re_investment + ct_revenues/1e3)/1e6:.2f} bn kZAR/yr"
    )

    # Step 4: extendable RE generators in the _R scenario
    add_gens = n.generators.query(
        "carrier in @reinvest_carriers and build_year == 2030 and p_nom_extendable"
    )

    if add_gens.empty:
        logger.warning(
            "add_ct_reinvestment_constraint: no extendable RE generators "
            "with build_year=2030 found — constraint skipped."
        )
        return

    # Step 5: linopy constraint
    # RHS = baseline RE investment (from reference) + CT revenues — both in scaled kZAR
    # capital_cost already divided by 1e3 via scale_costs; ct_revenues scaled equally
    p_nom = n.model.variables["Generator-p_nom"].sel({"Generator-ext": add_gens.index})
    costs = xr.DataArray(
        add_gens["capital_cost"].values,
        dims=["Generator-ext"],
        coords={"Generator-ext": add_gens.index.values}
    )
    lhs = (p_nom * costs).sum("Generator-ext")

    # on top of baseline: total RE investment >= base_investment + CT_revenues
    rhs = base_re_investment + ct_revenues / 1e3

    n.model.add_constraints(lhs >= rhs, name="ct_reinvestment")

    logger.info(
        f"CT reinvestment constraint added: "
        f"annualised RE investment >= base {base_re_investment/1e6:.2f} + "
        f"CT {ct_revenues/1e9:.2f} bn ZAR "
        f"({len(add_gens)} extendable RE generators)"
    )


def add_ct_reinvestment_constraint_multiyear(n, sns, SCENARIO_SETUP, snakemake):
    """
    Multi-period CT revenue recycling constraint (Paper 1).

    For each investment period y, reads base scenario emissions in period y,
    looks up the CT_2050 rate for year y, and enforces:
        annualized RE investment (build_year==y) >= base_RE_investment[y] + CT_revenues[y]

    Constraint is skipped for periods where CT_2050 rate == 0.
    Must be called after scale_costs(n, 1e3).
    """
    reinvest_carriers = ['wind', 'wind_low', 'solar_pv', 'solar_pv_low']
    # Storage carriers included in the reinvestment pool (alongside RE generators).
    # PHS excluded: resource-constrained, decades-long lead times, not a realistic
    # near-term CT reinvestment target in SA.
    reinvest_storage_carriers = ['battery_1h', 'battery_4h', 'battery_8h']

    # Load CT_2050 rate trajectory from emissions.xlsx
    working_folder = snakemake.config["scenarios"]["working_folder"]
    emis_xlsx = os.path.join("scenarios", working_folder, "sub_scenarios", "emissions.xlsx")
    ct_raw = pd.read_excel(emis_xlsx, sheet_name="carbon_tax", index_col=0)
    ct_row = ct_raw.loc["CT_2050"].drop("units").dropna()
    ct_row.index = ct_row.index.astype(int)  # year → R/tCO2

    # Base scenario paths
    base_scenario  = SCENARIO_SETUP.name.replace("_R", "")
    options        = snakemake.wildcards.options
    base_net_path  = os.path.join("results", working_folder, base_scenario, options, "networks", "solved.nc")
    base_emis_path = os.path.join("results", working_folder, base_scenario, options, "outputs", "generator_emissions.csv")

    n_base = pypsa.Network(base_net_path)
    gen_emissions = pd.read_csv(base_emis_path, index_col=0)
    gen_emissions.index = gen_emissions.index.astype(int)

    # Weighted annual generation per generator per period [MWh]
    w = n_base.snapshot_weightings["generators"]
    gen_p_annual = n_base.generators_t.p.mul(w, axis=0).groupby(level=0).sum()

    for y in n.investment_periods:
        ct_rate = ct_row.get(y, 0)
        if ct_rate == 0:
            logger.info(f"CT reinvestment multiyear [{SCENARIO_SETUP.name}]: period {y} — rate=0, skipping")
            continue

        if y not in gen_p_annual.index:
            logger.warning(f"CT reinvestment multiyear [{SCENARIO_SETUP.name}]: period {y} not in base generation, skipping")
            continue

        # snapshot_weightings["generators"] sums to ~8760h per period (verified: one
        # representative year). gen_p_annual.loc[y] is therefore already annual MWh.
        # Both LHS (p_nom * capital_cost, annualised kZAR/yr) and RHS (annual CT
        # revenues) are on the same annual basis — no years_in_period division needed.
        # 50% of annual CT revenues are reinvested in RE + storage; the other 50%
        # represents other government spending (social transfers, budget etc.).
        REINVEST_FRACTION = 0.5
        gen_p_y     = gen_p_annual.loc[y]                      # MWh/yr (annual)
        common      = gen_emissions.columns.intersection(gen_p_y.index)
        ef_y        = gen_emissions.loc[y, common] if y in gen_emissions.index else gen_emissions.iloc[-1][common]
        emissions_t = (gen_p_y[common] * ef_y).sum() / 1000   # tCO2/yr
        ct_revenues = ct_rate * emissions_t * REINVEST_FRACTION  # R/yr (50% reinvested)

        # Base scenario: annualised RE + storage investment built in period y
        base_re = n_base.generators.query(
            "carrier in @reinvest_carriers and build_year == @y and p_nom_extendable"
        )
        base_su = n_base.storage_units.query(
            "carrier in @reinvest_storage_carriers and build_year == @y and p_nom_extendable"
        )
        base_re_investment = (
            (base_re.p_nom_opt * base_re.capital_cost).sum()
            + (base_su.p_nom_opt * base_su.capital_cost).sum()
        )  # kZAR/yr

        logger.info(
            f"CT reinvestment multiyear [{SCENARIO_SETUP.name}] {y}: "
            f"{emissions_t/1e6:.2f} MtCO2/yr × {ct_rate} R/t × {REINVEST_FRACTION:.0%} "
            f"= {ct_revenues/1e9:.2f} bn ZAR/yr reinvested in RE+storage"
        )

        # _R scenario: extendable RE generators built in period y
        add_gens = n.generators.query(
            "carrier in @reinvest_carriers and build_year == @y and p_nom_extendable"
        )
        # _R scenario: extendable storage built in period y
        add_sus = n.storage_units.query(
            "carrier in @reinvest_storage_carriers and build_year == @y and p_nom_extendable"
        )
        if add_gens.empty and add_sus.empty:
            logger.warning(
                f"CT reinvestment multiyear [{SCENARIO_SETUP.name}] {y}: "
                "no extendable RE generators or storage found — skipping this period."
            )
            continue

        # LHS: sum of (p_nom × capital_cost) for RE generators + storage units
        lhs_parts = []
        if not add_gens.empty:
            p_nom = n.model.variables["Generator-p_nom"].sel({"Generator-ext": add_gens.index})
            costs = xr.DataArray(
                add_gens["capital_cost"].values,
                dims=["Generator-ext"],
                coords={"Generator-ext": add_gens.index.values}
            )
            lhs_parts.append((p_nom * costs).sum("Generator-ext"))
        if not add_sus.empty:
            s_nom = n.model.variables["StorageUnit-p_nom"].sel({"StorageUnit-ext": add_sus.index})
            su_costs = xr.DataArray(
                add_sus["capital_cost"].values,
                dims=["StorageUnit-ext"],
                coords={"StorageUnit-ext": add_sus.index.values}
            )
            lhs_parts.append((s_nom * su_costs).sum("StorageUnit-ext"))
        lhs = sum(lhs_parts)

        rhs = base_re_investment + ct_revenues / 1e3  # both in kZAR

        n.model.add_constraints(lhs >= rhs, name=f"ct_reinvestment_{y}")

        logger.info(
            f"CT reinvestment_{y} added: RE+storage invest >= {base_re_investment/1e6:.2f} "
            f"+ {ct_revenues/1e9:.2f} bn ZAR "
            f"({len(add_gens)} generators, {len(add_sus)} storage units)"
        )
# AM added -----------------------------------------------------------------------
