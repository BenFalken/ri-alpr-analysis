"""
Step 5: Statistical analysis for the chosen scope. All results go to output/<run>/.

Unit level (tracts or block groups):
  correlations, univariate_models, vif, multivariable_model,
  geography_correlations, controls_comparison, partial_correlations,
  morans_i, leave_one_out, interaction
Town level (statewide scope only):
  town_correlations   coverage per resident vs. town characteristics
  town_adoption       towns with cameras vs. towns without
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm
from esda.moran import Moran
from libpysal.weights import KNN, Queen
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor

import config as C
from helpers import fit_count_model, fit_fe_model, load_units, partial_spearman

GEO_CONTROLS = " + ".join(f"z_{v}" for v in C.GEO_VARS)


def report(df, name, title):
    print(f"\n=== {title} ===")
    print(df.round(3).to_string(index=False))
    df.to_csv(C.OUT / f"{name}.csv", index=False)


def irr_row(fit, coef, /, **labels):
    lo, hi = np.exp(fit.conf_int().loc[coef])
    return {**labels, "IRR_per_SD": np.exp(fit.params[coef]),
            "CI_low": lo, "CI_high": hi, "p": fit.pvalues[coef]}


def bh(pvals):
    return multipletests(pvals, method="fdr_bh")[1]


def correlations(u):
    blocks = []
    for out_col, out_label in C.OUTCOMES.items():
        rows = []
        for group, cols in C.VAR_GROUPS.items():
            for col in cols:
                rho, p = stats.spearmanr(u[col], u[out_col])
                rows.append({"group": group, "var": col, "variable": C.LABELS[col],
                             "outcome": out_label, "spearman_rho": rho, "p": p})
        block = pd.DataFrame(rows)
        block["p_adj_BH"] = bh(block.p)
        blocks.append(block)
    report(pd.concat(blocks, ignore_index=True), "correlations",
           "Spearman correlations (BH-adjusted within each camera measure)")


def univariate_models(u):
    rows = []
    for col, label in C.PREDICTORS.items():
        m, kind = fit_count_model(f"cameras ~ z_{col}", u)
        rows.append(irr_row(m, f"z_{col}", variable=label, model=kind))
    df = pd.DataFrame(rows)
    df["p_adj_BH"] = bh(df.p)
    report(df.sort_values("p"), "univariate_models", "One-variable count models (IRR per +1 SD)")


def multivariable_model(u):
    terms = ["z_log_income", "z_pct_black_nh", "z_pct_hispanic", "z_pop_density"]
    X = sm.add_constant(u[terms])
    vif = pd.DataFrame({"term": terms, "VIF": [variance_inflation_factor(X.values, i)
                                               for i in range(1, X.shape[1])]})
    report(vif, "vif", "Variance inflation factors (>5 = heavy overlap)")
    m, kind = fit_count_model("cameras ~ " + " + ".join(terms), u)
    report(pd.DataFrame([irr_row(m, t, term=t) for t in terms]),
           "multivariable_model", f"Multivariable model ({kind})")


def geography(u):
    adopting = None
    if C.SCOPE == "ri":
        per_town = u.groupby("town").cameras.sum()
        adopting = u[u.town.isin(per_town[per_town > 0].index)]
        print(f"\n{adopting.town.nunique()} of {u.town.nunique()} municipalities have "
              f"at least one camera ({len(adopting)} units)")

    rows = []
    for col in C.KEY_VARS:
        term, label = f"z_{col}", C.PREDICTORS[col]
        m, _ = fit_count_model(f"cameras ~ {term}", u)
        rows.append(irr_row(m, term, variable=label, model="Unadjusted"))
        m, _ = fit_count_model(f"cameras ~ {term} + {GEO_CONTROLS}", u)
        rows.append(irr_row(m, term, variable=label, model="Road & location controls"))
        if adopting is not None:
            m = fit_fe_model(f"cameras ~ {term} + {GEO_CONTROLS}", adopting)
            rows.append(irr_row(m, term, variable=label, model="+ within-town comparison"))
    report(pd.DataFrame(rows), "controls_comparison",
           "Associations before and after controls (IRR per +1 SD)")


def partial_correlations(u):
    geo = list(C.GEO_VARS)
    checks = [("pct_poverty", ["pct_renter"]), ("pct_renter", ["pct_poverty"])]
    checks += [(v, geo) for v in C.KEY_VARS]
    rows = []
    for x, ctrl in checks:
        r, p = partial_spearman(u, x, "cam_per_km2", ctrl)
        rows.append({"variable": x, "controlling_for": ", ".join(ctrl), "partial_r": r, "p": p})
    report(pd.DataFrame(rows), "partial_correlations",
           "Partial Spearman correlations with cameras per km²")


def spatial_autocorrelation(u):
    w = Queen.from_dataframe(u, use_index=False, silence_warnings=True)
    neighbors = "shared borders"
    if w.islands:  # e.g. Block Island, Jamestown: fall back to nearest neighbors
        pts = gpd.GeoDataFrame(geometry=u.representative_point().values, crs=u.crs)
        w = KNN.from_dataframe(pts, k=6)
        neighbors = "6 nearest neighbors"
    w.transform = "r"

    m, _ = fit_count_model(f"cameras ~ z_pct_poverty + {GEO_CONTROLS}", u)
    resid = u.cameras - m.predict(u, exposure=u.area_km2)
    rows = []
    for label, values in [("Camera density", u.cam_per_km2),
                          ("Controlled-model residuals", resid)]:
        mi = Moran(np.asarray(values, dtype=float), w, permutations=999)
        rows.append({"series": label, "morans_I": mi.I, "p": mi.p_sim, "neighbors": neighbors})
    report(pd.DataFrame(rows), "morans_i", "Moran's I (spatial autocorrelation)")


def leave_one_out(u):
    base, _ = stats.spearmanr(u.pct_poverty, u.cam_per_km2)
    rows = []
    for i in u.index:
        sub = u.drop(index=i)
        rho, p = stats.spearmanr(sub.pct_poverty, sub.cam_per_km2)
        rows.append({"dropped_unit": u.loc[i, "GEOID"], "town": u.loc[i, "town"],
                     "rho": rho, "p": p, "shift": abs(rho - base)})
    df = pd.DataFrame(rows).sort_values("shift", ascending=False)
    df.to_csv(C.OUT / "leave_one_out.csv", index=False)
    print(f"\n=== Leave-one-out: poverty vs. cameras per km² (full sample ρ = {base:.2f}) ===")
    print(f"ρ range {df.rho.min():.2f}–{df.rho.max():.2f}, "
          f"p range {df.p.min():.4f}–{df.p.max():.4f}")
    print(df.head(3).round(3).to_string(index=False))


def interaction(u):
    m, kind = fit_count_model("cameras ~ z_pct_poverty * z_pct_white_nh", u)
    term = "z_pct_poverty:z_pct_white_nh"
    report(pd.DataFrame([irr_row(m, term, term="poverty × % White", model=kind)]),
           "interaction", "Exploratory interaction")


def town_level():
    if C.SCOPE != "ri":
        return
    t = pd.read_csv(C.TOWNS_CSV)
    town_vars = {
        "median_hh_income_popwt": "Median household income (pop-weighted)",
        "pct_poverty": "% below poverty line",
        "pct_white_nh": "% White (non-Hispanic)",
        "pct_black_nh": "% Black (non-Hispanic)",
        "pct_hispanic": "% Hispanic",
        "pct_renter": "% renter-occupied",
        "pct_college": "% 25+ with bachelor's or higher",
        "pct_no_vehicle": "% households with no vehicle",
        "pop_density": "Population per km²",
        "population": "Total population",
    }

    rows = []
    for col, label in town_vars.items():
        rho, p = stats.spearmanr(t[col], t.cam_per_10k_pop)
        rows.append({"variable": label, "spearman_rho": rho, "p": p})
    df = pd.DataFrame(rows)
    df["p_adj_BH"] = bh(df.p)
    report(df.sort_values("p"), "town_correlations",
           f"Town level: cameras per 10k residents vs. town characteristics (n={len(t)})")

    adopt = t.cameras > 0
    rows = []
    for col, label in town_vars.items():
        a, b = t.loc[adopt, col], t.loc[~adopt, col]
        _, p = stats.mannwhitneyu(a, b)
        rows.append({"variable": label, "median_with_cameras": a.median(),
                     "median_without": b.median(), "p": p})
    df = pd.DataFrame(rows)
    df["p_adj_BH"] = bh(df.p)
    report(df.sort_values("p"), "town_adoption",
           f"Towns with cameras ({adopt.sum()}) vs. without ({(~adopt).sum()})")


def within_town_split(u, min_units=4, min_cameras=3):
    """Split each town's units at the town's median income; compare camera density
    in the lower- and higher-income halves. Sign test across towns."""
    if C.SCOPE != "ri":
        return
    rows = []
    for town, g in u.groupby("town"):
        if len(g) < min_units or g.cameras.sum() < min_cameras:
            continue
        lower = g.median_hh_income <= g.median_hh_income.median()
        lo, hi = g[lower], g[~lower]
        if lo.empty or hi.empty:
            continue
        rows.append({
            "town": town, "units": len(g), "cameras": g.cameras.sum(),
            "lower_income_cameras": lo.cameras.sum(),
            "higher_income_cameras": hi.cameras.sum(),
            "lower_income_cam_per_km2": lo.cameras.sum() / lo.area_km2.sum(),
            "higher_income_cam_per_km2": hi.cameras.sum() / hi.area_km2.sum(),
        })
    df = pd.DataFrame(rows)
    diff = df.lower_income_cam_per_km2 - df.higher_income_cam_per_km2
    k, n = int((diff > 0).sum()), int((diff != 0).sum())
    test = stats.binomtest(k, n, 0.5)
    report(df.sort_values("town"), "within_town_split",
           f"Within-town split: lower-income half has more cameras/km² in {k} of {n} towns "
           f"(sign test p = {test.pvalue:.3f})")
    pd.DataFrame([{"towns_lower_income_higher": k, "towns_compared": n,
                   "sign_test_p": test.pvalue}]).to_csv(
        C.OUT / "within_town_sign_test.csv", index=False)


if __name__ == "__main__":
    u = load_units()
    print(f"{C.S['label']}: {len(u)} {C.UNIT_LABEL}s, {u.cameras.sum()} cameras, "
          f"ACS {C.ACS_YEAR - 4}–{C.ACS_YEAR}")
    correlations(u)
    univariate_models(u)
    multivariable_model(u)
    geography(u)
    partial_correlations(u)
    spatial_autocorrelation(u)
    leave_one_out(u)
    interaction(u)
    within_town_split(u)
    town_level()