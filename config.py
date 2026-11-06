"""
Shared settings for the Rhode Island / Providence ALPR analysis.

Three settings choose what a run analyzes. run_all.py sets them from its
command-line flags; they can also be set as environment variables.
  ALPR_SCOPE     "providence" (city only) or "ri" (whole state)
  ALPR_LEVEL     "tract" or "bg" (block group: finer, but noisier estimates)
  ALPR_ACS_YEAR  last year of the ACS 5-year estimates (2024 = 2020-2024)
"""
import os
from pathlib import Path

SCOPE = os.environ.get("ALPR_SCOPE", "providence")
GEO_LEVEL = os.environ.get("ALPR_LEVEL", "tract")
ACS_YEAR = int(os.environ.get("ALPR_ACS_YEAR", "2024"))
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")  # optional

API_LEVEL = {"tract": "tract", "bg": "block group"}[GEO_LEVEL]
UNIT_LABEL = {"tract": "census tract", "bg": "block group"}[GEO_LEVEL]

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")  # required; see README

# ---- Scope-specific settings ----
SCOPES = {
    "providence": {
        "label": "Providence",
        "town": "Providence",   # keep only units in this municipality
        "geo_vars": {
            "road_km_per_km2":  "Major road km per km²",
            "dist_downtown_km": "Distance to downtown (km)",
            "dist_border_km":   "Distance to city border (km)",
        },
        "n_bins": 5,
    },
    "ri": {
        "label": "Rhode Island",
        "town": None,           # keep the whole state
        "geo_vars": {
            "road_km_per_km2": "Major road km per km²",
            "dist_highway_km": "Distance to interstate/expressway (km)",
            "dist_border_km":  "Distance to town border (km)",
        },
        "n_bins": 10,
    },
}
S = SCOPES[SCOPE]
GEO_VARS = S["geo_vars"]
N_BINS = S["n_bins"]

# ---- Folders ----
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUN_NAME = f"{SCOPE}_{GEO_LEVEL}_{ACS_YEAR}"
OUT = ROOT / "output" / RUN_NAME
FIG = OUT / "figures"
WARDS_OUT = ROOT / "output" / "providence_wards"
for d in (DATA / "osm", DATA / "acs", FIG, WARDS_OUT):
    d.mkdir(parents=True, exist_ok=True)

# ---- Inputs you supply ----
WARDS_SHP = DATA / "PVD_Wards_2020" / "PVD_Wards_2020.shp"  # pre-2022 wards
WARD_COL = "District_1"

# ---- Downloads (statewide, shared by every run) ----
CAMERAS_JSON = DATA / "osm" / "ri_alpr_cameras.json"
ROADS_GEOJSON = DATA / "osm" / "ri_major_roads.geojson"
ACS_CSV = DATA / "acs" / f"acs5_{ACS_YEAR}_{GEO_LEVEL}.csv"
REFRESH = False  # True = re-download even if cached

# ---- Per-run outputs ----
UNITS_GPKG = OUT / "units.gpkg"
TOWNS_CSV = OUT / "towns.csv"

# ---- Analysis options ----
FLOCK_ONLY = True       # False = all ALPR brands
MIN_POPULATION = 100    # skip near-empty units (parks, water, airports)

CRS_LONLAT = "EPSG:4326"
CRS_METERS = "EPSG:32619"          # UTM 19N, for areas and distances
DOWNTOWN_PVD = (-71.4128, 41.8240)  # Kennedy Plaza (lon, lat)

PREDICTORS = {
    "log_income":     "Median household income (log)",
    "pct_poverty":    "% below poverty line",
    "pct_white_nh":   "% White (non-Hispanic)",
    "pct_black_nh":   "% Black (non-Hispanic)",
    "pct_hispanic":   "% Hispanic",
    "pct_asian_nh":   "% Asian (non-Hispanic)",
    "pct_college":    "% 25+ with bachelor's or higher",
    "pct_renter":     "% renter-occupied",
    "pct_no_vehicle": "% households with no vehicle",
    "pop_density":    "Population per km²",
}

# Variable groups, used to organize tables and figures
VAR_GROUPS = {
    "Income & housing": ["log_income", "pct_poverty", "pct_college",
                         "pct_renter", "pct_no_vehicle"],
    "Race & ethnicity": ["pct_white_nh", "pct_black_nh", "pct_hispanic", "pct_asian_nh"],
    "Density & roads":  ["pop_density", *GEO_VARS],
}
LABELS = {**PREDICTORS, **GEO_VARS}

OUTCOMES = {
    "cam_per_km2":     "Cameras per km²",
    "cam_per_10k_pop": "Cameras per 10k residents",
    "cameras":         "Camera count",
}

# Variables re-tested with geographic (and, statewide, town) controls
KEY_VARS = ["pct_poverty", "pct_renter", "log_income", "pct_white_nh"]

# ---- OpenStreetMap / Overpass ----
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {
    "User-Agent": f"ri-alpr-analysis/1.0 ({os.environ.get('ALPR_CONTACT', 'set ALPR_CONTACT')})",
    "Accept": "application/json",
}

_RI = 'area["ISO3166-2"="US-RI"]->.ri;'

CAMERA_QUERY = f"""
[out:json][timeout:90];
{_RI}
node["surveillance:type"="ALPR"](area.ri);
out body;
"""

ROADS_QUERY = f"""
[out:json][timeout:180];
{_RI}
way["highway"~"^(motorway|trunk|primary|secondary)$"](area.ri);
out geom;
"""