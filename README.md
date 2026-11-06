# Rhode Island ALPR analysis

Where are automated license plate readers (ALPRs) in Rhode Island, and who lives near them?
This project maps Flock Safety cameras recorded in OpenStreetMap against neighborhood
demographics from the U.S. Census Bureau, for Providence and for the state as a whole.

## Setup

    conda env create -f environment.yml
    conda activate alpr

Two environment variables are needed:

    conda env config vars set CENSUS_API_KEY=your_key    # https://api.census.gov/data/key_signup.html
    conda env config vars set ALPR_CONTACT=you@example.com
    conda deactivate && conda activate alpr

Census keys must be activated via the emailed link, and can take up to an hour to
work on every Census server.

## Running

    python run_all.py --scope both              # Providence and statewide, census tracts
    python run_all.py --scope ri --level bg     # statewide, block groups
    python run_all.py --scope ri --start 5      # rerun analysis and figures only

Each run writes to `output/<scope>_<level>_<year>/`. Settings live in `config.py`.

## Pipeline

| Step | Script | Does |
|---|---|---|
| 1 | `01_fetch_osm.py` | Statewide ALPRs and major roads from OpenStreetMap (cached) |
| 2 | `02_fetch_acs.py` | ACS 5-year demographics for every RI tract or block group (cached) |
| 3 | `03_wards.py` | Providence ward counts and interactive map (Providence runs only) |
| 4 | `04_build_units.py` | Joins demographics, municipality, cameras and road geography |
| 5 | `05_analyze.py` | Correlations, count models, controls, robustness and within-town tests |
| 6 | `06_figures.py` | All figures |

## Methods

- **Unit of analysis:** census tracts (default) or block groups. Camera presence is measured
  as cameras per km², per 10,000 residents, and as raw counts.
- **Associations:** Spearman rank correlations, Benjamini–Hochberg adjusted for multiple tests.
- **Count models:** negative binomial (or Poisson with robust errors when it fails to fit),
  with unit area as exposure. Effects are reported per one-standard-deviation change.
- **Geographic controls:** major-road density, distance to an interstate/expressway (statewide)
  or to downtown (Providence), and distance to the municipal border.
- **Within-town comparison (statewide):** whether a municipality has cameras at all is a local
  purchasing decision. Town fixed effects compare neighborhoods only with others in the same
  town, among towns with at least one camera.

## Limitations

- OpenStreetMap camera data is crowdsourced (largely via DeFlock) and may be less complete in
  some areas, especially rural towns.
- Associations describe who lives near cameras, not why cameras were placed there.
- Block-group estimates carry large margins of error; use them to check tract-level results.
- Providence ward boundaries are the pre-2022 lines.

## Data sources

- Cameras and roads: © OpenStreetMap contributors, ODbL
- Demographics: U.S. Census Bureau, American Community Survey 5-year estimates (via API)
- Tract, block group and municipal boundaries: Census cartographic boundary files (via pygris)
- Ward boundaries: City of Providence. The original `.prj` mixes feet (horizontal) and meters
  (vertical), which newer GDAL versions reject; it was replaced with the standard EPSG:3438
  definition (original kept as `PVD_Wards_2020.prj.orig`).