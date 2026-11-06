# MP411 Tokyo flood and drainage analysis

This repository contains the data, notebooks, and visual outputs for a Tokyo
urban drainage and inundation analysis. The work focuses on the Koto area and
uses rainfall, river-level, geospatial, land-cover, and hydraulic data to
explore flood risk and drainage behaviour.

## What is included

The analysis is organised around three Jupyter notebooks:

- [`Drainage_analysis.ipynb`](./Drainage_analysis.ipynb) — drainage-area
  analysis, geospatial processing, satellite data access, land-cover
  classification, and rainfall-related analysis.
- [`Drainage_analysisV2.ipynb`](./Drainage_analysisV2.ipynb) — a revised
  version of the drainage analysis workflow.
- [`Hydraulic_analysis.ipynb`](./Hydraulic_analysis.ipynb) — hydraulic and
  inundation analysis for the study area.

The repository also contains:

- Tokyo administrative boundaries in
  [`tokyo_prefecture_limits/`](./tokyo_prefecture_limits/).
- OpenStreetMap extracts, including [`koto.osm.pbf`](./koto.osm.pbf).
- Rainfall and precipitation time series such as
  [`Tokyo_P_daily.csv`](./Tokyo_P_daily.csv),
  [`monthly_total_P_tokyo.csv`](./monthly_total_P_tokyo.csv), and the
  [`1872-1906.csv`](./1872-1906.csv),
  [`1907-1966.csv`](./1907-1966.csv), and
  [`1967-2026.csv`](./1967-2026.csv) historical series.
- River water-level observations for the Arakawa and Sumida rivers, including
  the station files in [`Japanese Data/`](./Japanese%20Data/).
- Koto inundation and simulation data in
  [`koto_drainage_simulation.csv`](./koto_drainage_simulation.csv) and
  [`shinsui_koutounaibu.csv`](./shinsui_koutounaibu.csv).
- Figures and an animation generated during the analysis, including
  [`surfaceclass+inun.png`](./surfaceclass%2Binun.png),
  [`TINresults.png`](./TINresults.png), and
  [`koto_drainage_animation_hourly.mp4`](./koto_drainage_animation_hourly.mp4).

## Analysis workflow

The notebooks follow this general process:

1. Load Tokyo boundary and OpenStreetMap data.
2. Read rainfall and river water-level observations.
3. Retrieve and process geospatial and satellite imagery where required.
4. Derive terrain, surface, and land-cover information for the study area.
5. Analyse rainfall and river-level behaviour.
6. Run or inspect drainage and hydraulic/inundation results.
7. Export maps, plots, tabular results, and an hourly animation.

Notebook paths are relative to the repository root. Run notebooks from that
directory so that paths such as `tokyo_prefecture_limits/...` and
`Japanese Data/...` resolve correctly.

## Requirements

The notebooks are written in Python and use the scientific Python and
geospatial ecosystem. The imports in the analysis include:

- Jupyter Notebook or JupyterLab
- `pandas`, `numpy`, and `matplotlib`
- `geopandas`
- `rasterio`
- `scikit-learn`
- `pystac-client`, `planetary-computer`, and `stackstac`

Some notebook cells may also require additional geospatial, plotting, or
animation libraries depending on which sections are run. No
`requirements.txt` or environment file is currently included, so the exact
environment should be recorded before reproducing published results.

## Getting started

1. Clone the repository and change into its root:

   ```bash
   git clone https://github.com/foozdemiroglu-gif/MP411-Tokyo.git
   cd MP411-Tokyo
   ```

2. Create and activate a Python environment, then install Jupyter and the
   packages listed above. For geospatial work, installing through
   [conda-forge](https://conda-forge.org/) is often the most reliable option.

3. Start Jupyter:

   ```bash
   jupyter lab
   ```

4. Open a notebook and run its cells from top to bottom. Start with
   [`Drainage_analysis.ipynb`](./Drainage_analysis.ipynb), then use
   [`Drainage_analysisV2.ipynb`](./Drainage_analysisV2.ipynb) or
   [`Hydraulic_analysis.ipynb`](./Hydraulic_analysis.ipynb) as appropriate.

If a notebook accesses Microsoft Planetary Computer/STAC data, an internet
connection is required and results may change as upstream datasets or
services are updated.

## Data and reproducibility notes

- The repository contains large raster/vector and time-series assets. Check
  available disk space before downloading or regenerating intermediate data.
- Several files are derived outputs rather than raw inputs. Their provenance
  is defined by the notebook cells that generate them.
- Keep the working directory at the repository root when executing notebooks;
  changing it may break relative paths.
- The notebooks should be treated as the executable record of the current
  analysis. For a reproducible study, pin the Python and dependency versions,
  document external data access dates, and save notebook outputs after a
  successful run.
- Do not commit credentials or tokens if an external data service requests
  authentication.

## Project status

This is a research and analysis workspace rather than a packaged Python
library. The notebooks and checked-in outputs represent the current state of
the analysis; there is no automated test suite or command-line entry point at
present.
