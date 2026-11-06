"""
Step 1: Download every ALPR and all major roads in Rhode Island from OpenStreetMap.

Statewide downloads are shared by every scope. Cached in data/osm/;
set REFRESH = True in config.py to re-download.
Outputs: data/osm/ri_alpr_cameras.json, data/osm/ri_major_roads.geojson
"""
import json

import geopandas as gpd
from shapely.geometry import LineString

import config as C
from helpers import fetch_overpass


def fetch_cameras():
    if C.CAMERAS_JSON.exists() and not C.REFRESH:
        print(f"Using cached {C.CAMERAS_JSON.name}")
        return
    data = fetch_overpass(C.CAMERA_QUERY)
    cameras = []
    for el in data.get("elements", []):
        if "lat" in el and "lon" in el:
            maker = el.get("tags", {}).get("manufacturer", "Unknown")
            cameras.append({
                "id": el["id"],
                "lat": el["lat"],
                "lon": el["lon"],
                "manufacturer": maker,
                "is_flock": "flock" in maker.lower(),
            })
    with open(C.CAMERAS_JSON, "w") as f:
        json.dump(cameras, f, indent=2)
    n_flock = sum(c["is_flock"] for c in cameras)
    print(f"Saved {len(cameras)} ALPRs ({n_flock} Flock) to {C.CAMERAS_JSON.name}")


def fetch_roads():
    if C.ROADS_GEOJSON.exists() and not C.REFRESH:
        print(f"Using cached {C.ROADS_GEOJSON.name}")
        return
    data = fetch_overpass(C.ROADS_QUERY)
    lines = [
        {"highway": el["tags"].get("highway"),
         "geometry": LineString([(p["lon"], p["lat"]) for p in el["geometry"]])}
        for el in data["elements"]
        if len(el.get("geometry", [])) > 1
    ]
    roads = gpd.GeoDataFrame(lines, crs=C.CRS_LONLAT)
    roads.to_file(C.ROADS_GEOJSON, driver="GeoJSON")
    print(f"Saved {len(roads)} road segments to {C.ROADS_GEOJSON.name}")


if __name__ == "__main__":
    fetch_cameras()
    fetch_roads()