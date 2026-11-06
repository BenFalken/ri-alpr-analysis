"""Functions shared by more than one step of the pipeline."""
import json
import time

import geopandas as gpd
import pandas as pd
import requests
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

import config as C

import warnings
import numpy as np


def fetch_overpass(query, max_retries=4):
    """POST a query to Overpass, retrying with backoff and falling back to a mirror."""
    for url in C.OVERPASS_ENDPOINTS:
        wait = 5
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.post(url, data={"data": query}, headers=C.HEADERS, timeout=240)
            except requests.RequestException as e:
                print(f"  {url} attempt {attempt}: {e}")
            else:
                if r.status_code == 200:
                    return r.json()
                print(f"  {url} attempt {attempt}: HTTP {r.status_code}")
                if r.status_code not in (429, 502, 503, 504):
                    print(r.text[:500])
                    break  # not a load problem; retrying won't help
            time.sleep(wait)
            wait *= 2
    raise SystemExit("All Overpass endpoints failed. Try again later.")


def load_cameras(flock_only=False):
    """Statewide camera list as a GeoDataFrame in lat/lon."""
    with open(C.CAMERAS_JSON) as f:
        df = pd.DataFrame(json.load(f))
    if "is_flock" not in df:
        df["is_flock"] = df.manufacturer.fillna("").str.lower().str.contains("flock")
    if flock_only:
        df = df[df.is_flock]
    return gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=C.CRS_LONLAT
    )


def load_units():
    """Analysis dataset from step 4, with z-scored copies of every predictor."""
    u = gpd.read_file(C.UNITS_GPKG)
    for col in list(C.PREDICTORS) + list(C.GEO_VARS):
        u[f"z_{col}"] = (u[col] - u[col].mean()) / u[col].std()
    return u


def union(geoms):
    return geoms.union_all() if hasattr(geoms, "union_all") else geoms.unary_union


def fit_count_model(formula, data):
    """Camera-count regression with unit area as exposure.
    Negative binomial if it fits cleanly; otherwise Poisson with robust SEs,
    which gives valid inference even when counts are overdispersed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            m = smf.negativebinomial(formula, data=data, exposure=data.area_km2).fit(
                disp=0, maxiter=500)
            if m.mle_retvals.get("converged", True) and np.all(np.isfinite(m.bse)):
                return m, "NegBin"
        except Exception:
            pass
        m = smf.glm(formula, data=data, family=sm.families.Poisson(),
                    exposure=data.area_km2).fit(cov_type="HC1")
        return m, "Poisson (robust SE)"


def fit_fe_model(formula, data, group_col="town"):
    """Poisson count model with town fixed effects; SEs clustered by town.
    Compares each unit only with other units in the same town."""
    data = data.assign(town_fe=data[group_col].astype("category"))
    groups = data.town_fe.cat.codes
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return smf.glm(formula + " + town_fe", data=data, family=sm.families.Poisson(),
                       exposure=data.area_km2).fit(cov_type="cluster",
                                                   cov_kwds={"groups": groups})


def partial_spearman(df, x, y, controls):
    """Spearman correlation of x and y after removing rank-linear effects of controls."""
    ranked = df[[x, y] + controls].rank()
    X = sm.add_constant(ranked[controls])
    rx = sm.OLS(ranked[x], X).fit().resid
    ry = sm.OLS(ranked[y], X).fit().resid
    return stats.pearsonr(rx, ry)


def stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""