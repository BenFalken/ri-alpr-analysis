"""
Step 2: Download ACS 5-year estimates for every tract or block group in Rhode Island
from the Census Bureau API.

Saves raw counts; percentages are computed in step 4 so towns can be built from
the same counts. Census codes for "not available" (large negatives) become blank.
Output: data/acs/acs5_<year>_<level>.csv
"""
import numpy as np
import pandas as pd
import requests

import config as C

COUNTIES = ["001", "003", "005", "007", "009"]  # Bristol, Kent, Newport, Providence, Washington

VARS = {
    "B01003_001E": "population",
    "B01002_001E": "median_age",
    # Race / ethnicity (B03002)
    "B03002_001E": "race_total",
    "B03002_003E": "white_nh",
    "B03002_004E": "black_nh",
    "B03002_006E": "asian_nh",
    "B03002_012E": "hispanic",
    # Income and poverty
    "B19013_001E": "median_hh_income",
    "C17002_001E": "pov_universe",
    "C17002_002E": "pov_under_050",   # income < 50% of poverty line
    "C17002_003E": "pov_050_099",     # 50-99% of poverty line
    # Housing tenure
    "B25003_001E": "tenure_total",
    "B25003_002E": "owner_occ",
    "B25003_003E": "renter_occ",
    "B25064_001E": "median_rent",
    # Education, age 25+
    "B15003_001E": "edu_total",
    "B15003_022E": "edu_ba",
    "B15003_023E": "edu_ma",
    "B15003_024E": "edu_prof",
    "B15003_025E": "edu_phd",
    # Vehicles available, by tenure
    "B25044_001E": "hh_vehicle_total",
    "B25044_003E": "owner_no_vehicle",
    "B25044_010E": "renter_no_vehicle",
}


import time  # add to the imports at the top

def fetch_county(county, max_retries=5):
    within = f"state:44 county:{county}"
    if C.API_LEVEL == "block group":
        within += " tract:*"
    params = {"get": ",".join(VARS), "for": f"{C.API_LEVEL}:*", "in": within,
              "key": C.CENSUS_API_KEY}
    url = f"https://api.census.gov/data/{C.ACS_YEAR}/acs/acs5"

    wait = 10
    for attempt in range(1, max_retries + 1):
        r = requests.get(url, params=params, timeout=90)
        if r.status_code == 200 and "_key.html" not in r.url:
            try:
                rows = r.json()
                return pd.DataFrame(rows[1:], columns=rows[0])
            except ValueError:
                pass  # fall through to retry
        reason = "key not recognized yet" if "_key.html" in r.url else f"HTTP {r.status_code}"
        print(f"  county {county} attempt {attempt}: {reason}; retrying in {wait}s")
        time.sleep(wait)
        wait *= 2

    raise SystemExit(
        f"Census API kept failing for county {county}.\n"
        f"Last URL: {r.url}\nResponse starts with:\n{r.text[:300]}\n"
        "A newly activated key can take up to an hour to work everywhere; try again later."
    )


def main():
    if C.ACS_CSV.exists() and not C.REFRESH:
        print(f"Using cached {C.ACS_CSV.name}")
        return

    df = pd.concat([fetch_county(c) for c in COUNTIES], ignore_index=True)

    geo_cols = ["state", "county", "tract"] + (["block group"] if C.GEO_LEVEL == "bg" else [])
    df["GEOID"] = df[geo_cols].astype(str).agg("".join, axis=1)
    df = df.drop(columns=geo_cols).rename(columns=VARS)

    for col in VARS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < 0, col] = np.nan

    df.to_csv(C.ACS_CSV, index=False)
    print(f"Saved {len(df)} {C.UNIT_LABEL}s to {C.ACS_CSV.name} "
          f"(ACS {C.ACS_YEAR - 4}-{C.ACS_YEAR})")


if __name__ == "__main__":
    main()
