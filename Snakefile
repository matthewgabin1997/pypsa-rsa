configfile: "config.yaml"

from os.path import normpath, exists, isdir
import pandas as pd
import os
import re
import socket
import numpy as np

PYPSA_ENV = os.environ["CONDA_PREFIX"]
shell.prefix(
    f"export PROJ_DATA={PYPSA_ENV}/share/proj; "
    f"export PROJ_LIB={PYPSA_ENV}/share/proj; "
    f"export GDAL_DATA={PYPSA_ENV}/share/gdal; "
    f"export PROJ_NETWORK=OFF; "
    f"export PYTHONUNBUFFERED=1; "
    f"export GRB_LICENSE_FILE={os.path.expanduser('~/gurobi.lic')}; "
)

scenarios = pd.read_excel(
    os.path.join("scenarios",config["scenarios"]["working_folder"], config["scenarios"]["setup"]),
    sheet_name="scenario_definition", 
    index_col=0
)
scenarios_to_run = scenarios[
    scenarios["run_scenario"].astype(str).str.strip().str.lower().isin(["1", "true"])
]


############################################################################################################
# Rules to run through all scenarios specified in the scenarios_to_run.xlsx file
############################################################################################################
rule solve_all:
    input:
        "results/solve_all_scenarios",
        "results/plot_all_scenarios",

############################################################################################################
# Rules to produce network topology
############################################################################################################
rule build_topology:
    input:
        supply_regions = config["data_paths"]["bundle"] + "/rsa_supply_regions.gpkg",
        existing_lines = config["data_paths"]["bundle"] + "/bundle/Existing_Lines.shp",
        planned_lines = config["data_paths"]["bundle"] + "/tdp_digitised/TDP_2023_32.shp",
        gdp_pop_data = config["data_paths"]["bundle"] + "/bundle/Mesozones.shp",
    output:
        buses = "resources/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/buses.geojson",
        lines = "resources/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/lines.geojson",
    script: "scripts/build_topology.py"


# Function to generate the input files based on the scenario and its respective years
def generate_networks():
    inputs = []
    for sc_id in scenarios_to_run.index:
        scenario = scenarios_to_run.loc[sc_id, "scenario"]
        options = scenarios_to_run.loc[sc_id, "options"]
        inputs.append("networks/" + config["scenarios"]["working_folder"] + f"/{scenario}/{options}/elec.nc")
    return inputs

def generate_scenarios():
    inputs = []
    for sc_id in scenarios_to_run.index:
        scenario = scenarios_to_run.loc[sc_id, "scenario"]
        options = scenarios_to_run.loc[sc_id, "options"]
        inputs.append("results/" + config["scenarios"]["working_folder"] + f"/{scenario}/{options}/networks/solved.nc")
    print(inputs)
    return inputs

rule build_all_scenarios:
    input:
        generate_networks()
    output:
        touch("results/build_all_scenarios")

rule solve_all_scenarios:
    input:
        generate_scenarios()
    output:
        touch("results/solve_all_scenarios")

def generate_plots():
    outputs = []
    for sc_id in scenarios_to_run.index:
        scenario = scenarios_to_run.loc[sc_id, "scenario"]
        options = scenarios_to_run.loc[sc_id, "options"]
        outputs.append("results/" + config["scenarios"]["working_folder"] + f"/{scenario}/{options}/outputs/plots/map_only.png")
    return outputs

rule plot_all_scenarios:
    input:
        generate_plots()
    output:
        touch("results/plot_all_scenarios")

rule plot_network:
    input:
        network = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/networks/solved.nc",
        supply_regions = "data/Shapefiles/11-supply.shp",
        resarea = "data/bundle/REDZ_DEA_Unpublished_Draft_2015/REDZ_DEA_Unpublished_Draft_2015.shp",
        gen_emissions = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/generator_emissions.csv",
    output:
        only_map = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/plots/map_only.png",
        ext = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/plots/map_full.png",
        pathway = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/plots/pathway.png",
    script:
        "scripts/plot_network_sa.py"

rule base_network:
    input:
        buses = "resources/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/buses.geojson",
        lines = "resources/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/lines.geojson",
    output:
        "networks/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/base-network.nc",
    script: "scripts/base_network.py"


rule add_electricity:
    input:
        base_network = "networks/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/base-network.nc",
        supply_regions = "resources/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/buses.geojson",
        load = config["data_paths"]["bundle"] + "/bundle/SystemEnergy2009_22.csv",
        eskom_profiles = config["data_paths"]["bundle"] + "/eskom_pu_profiles.csv",
        renewable_profiles = config["data_paths"]["bundle"] + "/bundle/renewable_profiles_dcac_125_mar26.nc",
    output:
        network = "networks/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/elec.nc",
        gen_emissions = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/generator_emissions.csv",
        gen_stand_by_emissions = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/generator_stand_by_emissions.csv",
    script: "scripts/add_electricity.py"

rule prepare_and_solve_network:
    input:
        network = "networks/"+ config["scenarios"]["working_folder"] + "/{scenario}/{options}/elec.nc",
        generator_emissions = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/generator_emissions.csv",
        # AM added: _R scenarios depend on their reference scenario being solved first
        base_network = lambda w: (
            "results/" + config["scenarios"]["working_folder"] + "/"
            + w.scenario.replace("_R", "") + "/" + w.options + "/networks/solved.nc"
            if w.scenario.endswith("_R") else []
        ),
        # AM added end
    output:
        network = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/networks/solved.nc",
        network_stats = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/network_stats.csv",
        generators = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/generators.csv",
        storage_units = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/storage_units.csv",
        capacity_value = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/capacity_value.csv",
        decom_status = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/decom_status.csv",
        full_outages = "results/" + config["scenarios"]["working_folder"] + "/{scenario}/{options}/outputs/full_outages.csv",
    threads: 32
    resources:
        solver_slots=1,
        mem_mb=200000,
    script:
        "scripts/prepare_and_solve_network.py"
