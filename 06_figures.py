"""
Step 6: Draw every figure for the chosen scope. Written to output/<run>/figures/.

  1_overview_maps.png         camera density beside income, poverty, housing and race
  1b_overview_maps_metro.png  same, zoomed to the Providence metro (statewide only)
  2_heatmap.png               correlations, grouped and sorted
  3_quantile_bars.png         camera density across quantiles of each characteristic
  4_controls_effect.png       associations before vs. after controls
  5_roads_poverty.png         cameras, major roads and poverty
  6_within_town.png           lower- vs. higher-income halves of each town (statewide only)
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter
from scipy import stats
from shapely.geometry import box

import config as C
from helpers import load_cameras, load_units, stars, union

# ---------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------
plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10.5,
    "axes.titleweight": "semibold",
    "axes.titlecolor": "#222222",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#9a9a9a",
    "axes.labelcolor": "#333333",
    "xtick.color": "#555555",
    "ytick.color": "#555555",
    "legend.frameon": False,
    "figure.facecolor": "white",
})

SUBTITLE = f"{C.S['label']} · {C.UNIT_LABEL}s · ACS {C.ACS_YEAR - 4}–{C.ACS_YEAR}"
CAM_WORD = "Flock cameras" if C.FLOCK_ONLY else "ALPRs"
STATE = C.SCOPE == "ri"
EDGE_LW = 0.15 if STATE else 0.5
PRIMARY = list(C.OUTCOMES.values())[0]
METRO_BBOX = (-71.53, 41.72, -71.33, 41.92)   # lon/lat: Providence and inner suburbs

GROUP_STYLE = {
    "Income & housing": {"color": "#1f7a72", "cmap": "GnBu"},
    "Race & ethnicity": {"color": "#6a4c93", "cmap": "BuPu"},
    "Density & roads":  {"color": "#b8741a", "cmap": "YlOrBr"},
}
CAMERA_COLOR = "#b8432f"
DIVERGING = LinearSegmentedColormap.from_list(
    "soft_diverging", ["#2f6690", "#8fb8d8", "#f6f4f0", "#f0a07a", "#b8432f"])
CONTROL_COLORS = ["#9aa5ad", "#c4512f", "#2f4858"]

MAP_VARS = ["log_income", "pct_poverty", "pct_renter", "pct_no_vehicle",
            "pct_white_nh", "pct_black_nh", "pct_hispanic"]


def group_of(col):
    return next(g for g, cols in C.VAR_GROUPS.items() if col in cols)


def fmt_value(col, v):
    if col in ("log_income", "median_hh_income"):
        return f"${v / 1000:.0f}k"
    if col == "pop_density":
        return f"{v:,.0f}"
    if col.startswith("pct_"):
        return f"{v:.0f}%"
    return f"{v:.1f}"


def legend_fmt(col):
    if col == "median_hh_income":
        return "${:,.0f}"
    if col == "pop_density":
        return "{:,.0f}"
    if col.startswith("pct_"):
        return "{:.0f}%"
    return "{:.2f}"


def save(fig, name):
    fig.savefig(C.FIG / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote figures/{name}")


# ---------------------------------------------------------------
# 1. Overview maps (small multiples)
# ---------------------------------------------------------------
def effect_lookup():
    corr = pd.read_csv(C.OUT / "correlations.csv")
    corr = corr[corr.outcome == PRIMARY].set_index("var")
    ctrl = pd.read_csv(C.OUT / "controls_comparison.csv")
    most_controlled = ctrl.groupby("variable").tail(1).set_index("variable")
    return corr, most_controlled


def fig_overview_maps(u, cams, towns, extent=None, name="1_overview_maps.png", note=""):
    corr, ctrl = effect_lookup()
    adj_word = "within-town" if STATE else "road-adjusted"
    zoomed = extent is not None

    fig, axes = plt.subplots(2, 4, figsize=(18, 10.5))
    for ax, col in zip(axes.flat, ["cam_per_km2"] + MAP_VARS):
        if col == "cam_per_km2":
            u[u.cameras == 0].plot(ax=ax, color="#ececec", edgecolor="white", linewidth=EDGE_LW)
            u[u.cameras > 0].plot(
                ax=ax, column=col, scheme="quantiles", k=4, cmap="Reds",
                edgecolor="white", linewidth=EDGE_LW, legend=True,
                legend_kwds={"fmt": "{:.1f}", "loc": "lower left", "fontsize": 7,
                             "title": "per km² (grey = none)", "title_fontsize": 7})
            cams.plot(ax=ax, color="#1a1a1a", alpha=0.7, zorder=4,
                      markersize=1.5 if (STATE and not zoomed) else 5)
            title, line, color = f"{CAM_WORD} per km²", f"{len(cams)} cameras", CAMERA_COLOR
        else:
            plot_col = "median_hh_income" if col == "log_income" else col
            group = group_of(col)
            u.plot(ax=ax, column=plot_col, scheme="quantiles", k=5,
                   cmap=GROUP_STYLE[group]["cmap"], edgecolor="white", linewidth=EDGE_LW,
                   legend=True, legend_kwds={"fmt": legend_fmt(plot_col),
                                             "loc": "lower left", "fontsize": 7})
            r = corr.loc[col]
            line = f"ρ = {r.spearman_rho:+.2f}{stars(r.p_adj_BH)}"
            label = C.PREDICTORS[col]
            if label in ctrl.index:
                c = ctrl.loc[label]
                line += f"   ·   {adj_word} {c.IRR_per_SD:.2f}×{stars(c.p)}"
            title, color = label.replace(" (log)", ""), GROUP_STYLE[group]["color"]

        if towns is not None:
            towns.boundary.plot(ax=ax, color="#555555", linewidth=0.35, alpha=0.7)
        if zoomed:
            ax.set_xlim(extent[0], extent[2])
            ax.set_ylim(extent[1], extent[3])
            if col == "cam_per_km2" and towns is not None:
                for town, geom in towns.geometry.items():
                    p = geom.representative_point()
                    if extent[0] < p.x < extent[2] and extent[1] < p.y < extent[3]:
                        ax.text(p.x, p.y, town, fontsize=6.5, color="#333333",
                                ha="center", alpha=0.85, zorder=5)
        ax.set_axis_off()
        ax.set_title(title, loc="left", color=color, pad=14)
        ax.text(0, 1.005, line, transform=ax.transAxes, fontsize=8.5, color="#555555",
                va="bottom")

    fig.suptitle(f"{SUBTITLE}{note}", fontsize=13, fontweight="semibold", x=0.01, ha="left")
    fig.text(0.01, 0.005,
             "Shading: quantiles of each variable.  ρ: rank correlation with cameras per km².  "
             f"{adj_word.capitalize()}: change in expected cameras per +1 SD"
             + (" comparing tracts within the same town, controlling for roads." if STATE
                else ", controlling for roads and location.")
             + "   * p<0.05  ** p<0.01  *** p<0.001",
             fontsize=8, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    save(fig, name)


# ---------------------------------------------------------------
# 2. Grouped, sorted correlation heatmap
# ---------------------------------------------------------------
def fig_heatmap():
    df = pd.read_csv(C.OUT / "correlations.csv")
    outcomes = list(C.OUTCOMES.values())
    norm = Normalize(-0.6, 0.6, clip=True)

    rows, blocks, y = [], [], 0.0
    for group, cols in C.VAR_GROUPS.items():
        order = (df[(df.group == group) & (df.outcome == PRIMARY)]
                 .sort_values("spearman_rho")["var"].tolist())
        y += 0.9                                   # room for the group heading
        blocks.append((group, y, len(order)))
        for var in order:
            rows.append((var, y))
            y += 1
        y += 0.35

    fig, ax = plt.subplots(figsize=(8.5, 0.42 * y + 1.8))
    for var, yy in rows:
        for j, out in enumerate(outcomes):
            r = df[(df["var"] == var) & (df.outcome == out)].iloc[0]
            ax.add_patch(Rectangle((j, yy), 1, 1, facecolor=DIVERGING(norm(r.spearman_rho)),
                                   edgecolor="white", linewidth=2.5))
            ax.text(j + 0.5, yy + 0.5, f"{r.spearman_rho:+.2f}{stars(r.p_adj_BH)}",
                    ha="center", va="center", fontsize=9,
                    color="white" if abs(r.spearman_rho) > 0.42 else "#222222")
        ax.text(-0.12, yy + 0.5, C.LABELS[var].replace(" (log)", ""),
                ha="right", va="center", fontsize=9, color="#333333")

    for group, top, n in blocks:
        color = GROUP_STYLE[group]["color"]
        ax.add_patch(Rectangle((-0.07, top), 0.035, n, facecolor=color, edgecolor="none"))
        ax.text(-0.07, top - 0.2, group.upper(), ha="left", va="bottom", fontsize=8.5,
                fontweight="bold", color=color)

    for j, out in enumerate(outcomes):
        ax.text(j + 0.5, -0.15, out, ha="center", va="bottom", fontsize=9.5,
                fontweight="semibold", color="#222222")

    ax.set_xlim(-0.1, len(outcomes))
    ax.set_ylim(y, -0.6)
    ax.axis("off")

    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=DIVERGING), ax=ax,
                      orientation="horizontal", fraction=0.03, pad=0.02, shrink=0.55)
    cb.set_label("Spearman ρ   ← fewer cameras  ·  more cameras →", fontsize=8.5)
    cb.outline.set_visible(False)
    fig.suptitle(f"Where {CAM_WORD.lower()} are, by neighborhood characteristic\n{SUBTITLE}",
                 fontsize=11.5, fontweight="semibold")
    fig.text(0.5, 0.005, "Sorted within each group from negative to positive (cameras per km²).  "
             "* p<0.05  ** p<0.01  *** p<0.001, BH-adjusted",
             ha="center", fontsize=8, color="#666666")
    save(fig, "2_heatmap.png")


# ---------------------------------------------------------------
# 3. Quantile bars, one row per variable group
# ---------------------------------------------------------------
def fig_quantile_bars(u):
    overall = u.cameras.sum() / u.area_km2.sum()
    ncols = max(len(cols) for cols in C.VAR_GROUPS.values())
    nrows = len(C.VAR_GROUPS)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.4 * ncols, 3.4 * nrows),
                             sharey=True, squeeze=False)

    for r, (group, cols) in enumerate(C.VAR_GROUPS.items()):
        style = GROUP_STYLE[group]
        for c in range(ncols):
            ax = axes[r, c]
            if c >= len(cols):
                ax.set_visible(False)
                continue
            col = cols[c]
            src = "median_hh_income" if col == "log_income" else col
            bins = pd.qcut(u[src], C.N_BINS, duplicates="drop")
            g = u.groupby(bins, observed=True).agg(
                cameras=("cameras", "sum"), area=("area_km2", "sum"))
            rate = g.cameras / g.area
            lo = (stats.chi2.ppf(0.025, 2 * g.cameras) / 2 / g.area).fillna(0)
            hi = stats.chi2.ppf(0.975, 2 * (g.cameras + 1)) / 2 / g.area

            x = np.arange(len(g))
            ax.grid(axis="y", color="#ececec", linewidth=0.8, zorder=0)
            ax.bar(x, rate, width=0.8, zorder=2,
                   color=plt.get_cmap(style["cmap"])(np.linspace(0.35, 0.9, len(g))))
            ax.vlines(x, lo, hi, color="#2b2b2b", alpha=0.5, linewidth=1, zorder=3)
            ax.axhline(overall, color="#7a7a7a", linestyle=(0, (3, 3)), linewidth=0.9, zorder=1)

            floor = u[src].min()
            ax.set_xticks(x, [f"{fmt_value(src, max(iv.left, floor))}–{fmt_value(src, iv.right)}"
                              for iv in g.index], rotation=45, ha="right", fontsize=6.5)
            ax.tick_params(length=0)
            ax.spines["left"].set_visible(False)
            ax.set_title(C.LABELS[col].replace(" (log)", ""), loc="left", fontsize=9.5)

        axes[r, 0].set_ylabel("Cameras per km²")
        axes[r, 0].annotate(group.upper(), xy=(0, 1.22), xycoords="axes fraction",
                            fontsize=9, fontweight="bold", color=style["color"])

    tile = {5: "quintile", 10: "decile"}.get(C.N_BINS, f"{C.N_BINS}-tile")
    fig.suptitle(f"{CAM_WORD} per km² by {tile}   ·   {SUBTITLE}", fontsize=12,
                 fontweight="semibold", x=0.01, ha="left")
    fig.text(0.01, 0.0, "Bars: pooled rate (total cameras ÷ total area) per bin.  "
             "Lines: 95% confidence interval.  Dashed: overall rate.  "
             f"About {len(u) // C.N_BINS} {C.UNIT_LABEL}s per bar.",
             fontsize=8, color="#666666")
    fig.tight_layout(h_pad=3.5, rect=(0, 0.02, 1, 0.97))
    save(fig, "3_quantile_bars.png")


# ---------------------------------------------------------------
# 4. Before vs. after controls
# ---------------------------------------------------------------
def fig_controls_effect():
    df = pd.read_csv(C.OUT / "controls_comparison.csv")
    variables = list(dict.fromkeys(df.variable))
    models = list(dict.fromkeys(df.model))
    offsets = np.linspace(-0.22, 0.22, len(models)) if len(models) > 1 else [0]

    fig, ax = plt.subplots(figsize=(10, 1.4 * len(variables) + 1.4))
    for model, color, off in zip(models, CONTROL_COLORS, offsets):
        sub = df[df.model == model].set_index("variable").loc[variables]
        y = np.arange(len(variables)) + off
        ax.errorbar(sub.IRR_per_SD, y,
                    xerr=[sub.IRR_per_SD - sub.CI_low, sub.CI_high - sub.IRR_per_SD],
                    fmt="o", color=color, capsize=0, elinewidth=2, markersize=7, label=model)
        for yi, hi, p in zip(y, sub.CI_high, sub.p):
            ax.text(hi * 1.03, yi, f"p = {p:.3f}", va="center", fontsize=8, color=color)

    lo_lim = min(df.CI_low.min() * 0.85, 0.8)
    hi_lim = max(df.CI_high.max() * 1.4, 1.25)
    ax.axvline(1, color="#333333", linewidth=1)
    ax.set_xscale("log")
    ax.set_xlim(lo_lim, hi_lim)
    ticks = [t for t in [0.25, 0.33, 0.5, 0.67, 1, 1.5, 2, 3, 4] if lo_lim <= t <= hi_lim]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}×"))
    ax.xaxis.set_minor_locator(FixedLocator([]))
    ax.grid(axis="x", color="#ececec")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_yticks(range(len(variables)), [v.replace(" (log)", "") for v in variables])
    ax.invert_yaxis()
    ax.set_xlabel("Multiplier on expected cameras per +1 SD (95% CI, log scale)\n"
                  "left of 1× = fewer cameras · right of 1× = more")
    ax.set_title(f"How associations change with controls\n{SUBTITLE}", loc="left")
    ax.legend(loc="best", fontsize=8.5)
    save(fig, "4_controls_effect.png")


# ---------------------------------------------------------------
# 5. Roads and poverty
# ---------------------------------------------------------------
def fig_roads_poverty(u, cams, towns):
    roads = gpd.clip(gpd.read_file(C.ROADS_GEOJSON).to_crs(u.crs), union(u.geometry))
    scale = 0.6 if STATE else 1.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8),
                                   gridspec_kw={"width_ratios": [1, 1.1]})
    u.plot(column="pct_poverty", cmap="Purples", legend=True, edgecolor="white",
           linewidth=EDGE_LW, ax=ax1,
           legend_kwds={"label": "% below poverty line", "shrink": 0.6})
    for hw, lw in {"motorway": 2.2, "trunk": 1.8, "primary": 1.1, "secondary": 0.6}.items():
        sub = roads[roads.highway == hw]
        if len(sub):
            sub.plot(ax=ax1, color="#2c3e50", linewidth=lw * scale)
    cams.plot(ax=ax1, color=CAMERA_COLOR, markersize=(4 if STATE else 8) * 1.6,
              edgecolor="black", linewidth=0.3, zorder=5)
    if towns is not None:
        towns.boundary.plot(ax=ax1, color="#555555", linewidth=0.35, alpha=0.7)
    ax1.set_title(f"{CAM_WORD} (red), major roads and poverty", loc="left")
    ax1.set_axis_off()

    sc = ax2.scatter(u.road_km_per_km2, u.cam_per_km2, c=u.pct_poverty, cmap="Purples",
                     edgecolor="#333333", s=25 if STATE else 60, vmin=0, linewidth=0.5)
    cb = fig.colorbar(sc, ax=ax2, label="% below poverty line", shrink=0.8)
    cb.outline.set_visible(False)
    rho, p = stats.spearmanr(u.road_km_per_km2, u.cam_per_km2)
    ax2.set_xlabel(f"Major road length per km² of {C.UNIT_LABEL}")
    ax2.set_ylabel("Cameras per km²")
    ax2.set_title(f"Camera density vs. road density  (ρ = {rho:.2f}, p = {p:.3f})", loc="left")
    ax2.grid(color="#ececec")
    fig.suptitle(SUBTITLE, x=0.01, ha="left", fontweight="semibold")
    fig.tight_layout()
    save(fig, "5_roads_poverty.png")


# ---------------------------------------------------------------
# 6. Within-town split (statewide only)
# ---------------------------------------------------------------
def fig_within_town():
    path = C.OUT / "within_town_split.csv"
    if not STATE or not path.exists():
        return
    df = pd.read_csv(path)
    df["diff"] = df.lower_income_cam_per_km2 - df.higher_income_cam_per_km2
    df = df.sort_values("diff").reset_index(drop=True)
    test = pd.read_csv(C.OUT / "within_town_sign_test.csv").iloc[0]

    low_c, high_c = "#c4512f", "#2f6f8f"
    fig, ax = plt.subplots(figsize=(9.5, 0.45 * len(df) + 2))
    y = np.arange(len(df))
    for yi, a, b in zip(y, df.higher_income_cam_per_km2, df.lower_income_cam_per_km2):
        ax.plot([a, b], [yi, yi], color=low_c if b > a else high_c, alpha=0.3,
                linewidth=4, solid_capstyle="round", zorder=1)
    ax.scatter(df.higher_income_cam_per_km2, y, color=high_c, s=60, zorder=2,
               label="Higher-income half of town")
    ax.scatter(df.lower_income_cam_per_km2, y, color=low_c, s=60, zorder=3,
               label="Lower-income half of town")

    ax.set_yticks(y, [f"{t}  ({n})" for t, n in zip(df.town, df.units)])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color="#ececec")
    ax.set_xlabel(f"{CAM_WORD} per km²")
    ax.legend(loc="lower right", fontsize=8.5)
    k, n, p = int(test.towns_lower_income_higher), int(test.towns_compared), test.sign_test_p
    ax.set_title(f"In {k} of {n} towns, lower-income neighborhoods have more cameras per km²\n"
                 f"Sign test p = {p:.3f}   ·   {SUBTITLE}", loc="left")
    fig.text(0.01, 0.0, f"Each town's {C.UNIT_LABEL}s are split at the town's median household "
             f"income. Towns with at least 4 {C.UNIT_LABEL}s and 3 cameras; "
             f"number of {C.UNIT_LABEL}s in parentheses.",
             fontsize=8, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    save(fig, "6_within_town.png")


if __name__ == "__main__":
    u = load_units()
    cams = load_cameras(flock_only=C.FLOCK_ONLY).to_crs(u.crs)
    cams = gpd.sjoin(cams, u[["geometry"]], predicate="within").drop(columns="index_right")
    towns = u[["town", "geometry"]].dissolve("town") if STATE else None

    fig_overview_maps(u, cams, towns)
    if STATE:
        metro = gpd.GeoSeries([box(*METRO_BBOX)], crs=C.CRS_LONLAT).to_crs(u.crs).total_bounds
        fig_overview_maps(u, cams, towns, extent=metro,
                          name="1b_overview_maps_metro.png", note=" · Providence metro")
    fig_heatmap()
    fig_quantile_bars(u)
    fig_controls_effect()
    fig_roads_poverty(u, cams, towns)
    fig_within_town()