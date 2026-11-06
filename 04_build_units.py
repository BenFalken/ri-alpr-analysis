"""
Step 4: Build the analysis dataset for the chosen scope and geographic level.

For each tract or block group: ACS demographics, its municipality, camera count,
and geography measures (major roads, distance to highways, downtown, town border).
Also totals every measure by municipality.
Outputs: output/<run>/units.gpkg, output/<run>/towns.csv
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pygris import block_groups, county_subdivisions, tracts
from shapely.geometry import Point

import config as C
from helpers import load_cameras, union

COUNT_COLS = [
    "population", "race_total", "white_nh", "black_nh", "asian_nh", "hispanic",
    "pov_universe", "pov_under_050", "pov_050_099", "tenure_total", "owner_occ",
    "renter_occ", "edu_total", "edu_ba", "edu_ma", "edu_prof", "edu_phd",
    "hh_vehicle_total", "owner_no_vehicle", "renter_no_vehicle",
]


def pct(num, den):
    return 100 * num / den.where(den > 0)


def add_rates(df):
    """Percentages from raw ACS counts. Works for units and for summed towns."""
    df["pct_white_nh"] = pct(df.white_nh, df.race_total)
    df["pct_black_nh"] = pct(df.black_nh, df.race_total)
    df["pct_asian_nh"] = pct(df.asian_nh, df.race_total)
    df["pct_hispanic"] = pct(df.hispanic, df.race_total)
    df["pct_poverty"] = pct(df.pov_under_050 + df.pov_050_099, df.pov_universe)
    df["pct_renter"] = pct(df.renter_occ, df.tenure_total)
    df["pct_college"] = pct(df.edu_ba + df.edu_ma + df.edu_prof + df.edu_phd, df.edu_total)
    df["pct_no_vehicle"] = pct(df.owner_no_vehicle + df.renter_no_vehicle, df.hh_vehicle_total)
    return df


def load_boundaries():
    fetch = tracts if C.GEO_LEVEL == "tract" else block_groups
    units = fetch(state="RI", year=C.ACS_YEAR, cb=True, cache=True)[["GEOID", "geometry"]]
    towns = county_subdivisions(state="RI", year=C.ACS_YEAR, cb=True, cache=True)
    towns = towns[["NAME", "geometry"]].rename(columns={"NAME": "town"})
    return units.to_crs(C.CRS_METERS), towns.to_crs(C.CRS_METERS)


def assign_towns(units, towns):
    """Each unit's municipality, from a point guaranteed to lie inside it."""
    pts = gpd.GeoDataFrame(units[["GEOID"]], geometry=units.representative_point(),
                           crs=units.crs)
    hit = gpd.sjoin(pts, towns, predicate="within").drop_duplicates("GEOID")
    return units.GEOID.map(hit.set_index("GEOID").town)


def road_km(units, roads):
    """Length of major road (km) inside each unit."""
    pairs = gpd.sjoin(roads[["geometry"]], units[["GEOID", "geometry"]], predicate="intersects")
    shapes = units.set_index("GEOID").geometry
    lengths = shapely.length(shapely.intersection(
        np.asarray(pairs.geometry.values), np.asarray(shapes.loc[pairs.GEOID].values)))
    return pd.Series(lengths / 1000).groupby(pairs.GEOID.values).sum()


def main():
    acs = pd.read_csv(C.ACS_CSV, dtype={"GEOID": str})
    shapes, towns = load_boundaries()
    units = shapes.merge(acs, on="GEOID")
    print(f"{len(units)} {C.UNIT_LABEL}s with ACS data statewide")

    # Municipality, then restrict to scope
    units["town"] = assign_towns(units, towns)
    units = units.dropna(subset=["town"])
    if C.S["town"]:
        units = units[units.town == C.S["town"]].copy()
    print(f"{len(units)} {C.UNIT_LABEL}s in scope ({C.S['label']}), "
          f"{units.town.nunique()} municipalities")

    # Demographic rates
    units = add_rates(units)
    units["log_income"] = np.log(units.median_hh_income)
    units["area_km2"] = units.area / 1e6
    units["pop_density"] = units.population / units.area_km2

    # Cameras per unit
    cams = load_cameras(flock_only=C.FLOCK_ONLY).to_crs(units.crs)
    hits = gpd.sjoin(cams, units[["GEOID", "geometry"]], predicate="within")
    units["cameras"] = units.GEOID.map(hits.groupby("GEOID").size()).fillna(0).astype(int)
    print(f"{units.cameras.sum()} {'Flock ' if C.FLOCK_ONLY else ''}cameras in scope")

    # Geography
    roads = gpd.read_file(C.ROADS_GEOJSON).to_crs(units.crs)
    units["major_road_km"] = units.GEOID.map(road_km(units, roads)).fillna(0)
    units["road_km_per_km2"] = units.major_road_km / units.area_km2

    pts = np.asarray(units.representative_point().values)
    highways = union(roads[roads.highway.isin(["motorway", "trunk"])].geometry)
    units["dist_highway_km"] = shapely.distance(pts, highways) / 1000

    downtown = gpd.GeoSeries([Point(*C.DOWNTOWN_PVD)], crs=C.CRS_LONLAT).to_crs(units.crs).iloc[0]
    units["dist_downtown_km"] = shapely.distance(pts, downtown) / 1000

    borders = towns.set_index("town").geometry.boundary
    units["dist_border_km"] = shapely.distance(
        pts, np.asarray(borders.loc[units.town].values)) / 1000

    # Town totals, built from raw counts (before dropping sparse units)
    t = units.groupby("town")[COUNT_COLS + ["cameras", "area_km2"]].sum()
    t = add_rates(t)
    has_inc = units.median_hh_income.notna()
    t["median_hh_income_popwt"] = (
        (units.median_hh_income * units.population)[has_inc].groupby(units.town).sum()
        / units.population[has_inc].groupby(units.town).sum())
    t["pop_density"] = t.population / t.area_km2
    t["cam_per_10k_pop"] = t.cameras / t.population * 1e4
    t["cam_per_km2"] = t.cameras / t.area_km2
    t.reset_index().round(4).to_csv(C.TOWNS_CSV, index=False)

    # Drop units too sparse to analyze
    keep = (units.population >= C.MIN_POPULATION) & units[list(C.PREDICTORS)].notna().all(axis=1)
    if (~keep).any():
        print(f"Dropping {(~keep).sum()} sparse or incomplete units "
              f"({units.cameras[~keep].sum()} cameras in them)")
    units = units[keep].copy()

    units["cam_per_km2"] = units.cameras / units.area_km2
    units["cam_per_10k_pop"] = units.cameras / units.population * 1e4

    units.to_file(C.UNITS_GPKG, driver="GPKG")
    print(f"Wrote {C.RUN_NAME}/units.gpkg ({len(units)} units, {units.cameras.sum()} cameras) "
          f"and towns.csv")


if __name__ == "__main__":
    main()