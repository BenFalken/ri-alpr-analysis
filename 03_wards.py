"""
Step 3 (Providence only): Assign each ALPR to a city council ward; count and map.

Uses all ALPR brands, with Flock flagged. Ward boundaries are pre-2022.
Outputs: output/providence_wards/ward_summary.csv, cameras_by_ward.csv, ward_map.html
"""
import geopandas as gpd

import config as C
from helpers import load_cameras


def main():
    wards = gpd.read_file(C.WARDS_SHP).to_crs(C.CRS_LONLAT)
    if C.WARD_COL not in wards.columns:
        raise SystemExit(f"'{C.WARD_COL}' not in ward file. Columns: {list(wards.columns)}")

    # Statewide camera file -> keep only cameras inside a ward
    cams = gpd.sjoin(load_cameras(), wards[[C.WARD_COL, "geometry"]],
                     predicate="within").drop(columns="index_right")
    cams.drop(columns="geometry").to_csv(C.WARDS_OUT / "cameras_by_ward.csv", index=False)
    print(f"{len(cams)} ALPRs inside Providence wards")

    counts = cams.groupby(C.WARD_COL).agg(
        camera_count=("id", "size"), flock_count=("is_flock", "sum"))
    summary = wards[[C.WARD_COL, "geometry"]].merge(counts, on=C.WARD_COL, how="left")
    summary[["camera_count", "flock_count"]] = (
        summary[["camera_count", "flock_count"]].fillna(0).astype(int))
    summary["area_km2"] = (summary.to_crs(C.CRS_METERS).area / 1e6).round(2)
    summary["cameras_per_km2"] = (summary.camera_count / summary.area_km2).round(2)

    table = summary.drop(columns="geometry").sort_values("camera_count", ascending=False)
    print(table.to_string(index=False))
    table.to_csv(C.WARDS_OUT / "ward_summary.csv", index=False)

    m = summary.explore(
        column="camera_count", cmap="Reds", legend=True, tiles="Esri.WorldGrayCanvas",
        tooltip=[C.WARD_COL, "camera_count", "flock_count", "cameras_per_km2"],
    )
    cams.explore(m=m, column="is_flock", cmap=["black", "blue"],
                 marker_kwds={"radius": 4}, tooltip=["id", "manufacturer"])
    m.save(C.WARDS_OUT / "ward_map.html")
    print("Wrote output/providence_wards/")


if __name__ == "__main__":
    main()
