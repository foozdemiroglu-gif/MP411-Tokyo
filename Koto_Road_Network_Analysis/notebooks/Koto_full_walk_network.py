import os
import sys
from pathlib import Path
from datetime import datetime

# --------------------------------------------------
# 1. Set GDAL / PROJ paths before importing GIS packages
# --------------------------------------------------
env_path = Path(sys.prefix)

gdal_path = env_path / "Library" / "share" / "gdal"
proj_path = env_path / "Library" / "share" / "proj"

if gdal_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_path)

if proj_path.exists():
    os.environ["PROJ_LIB"] = str(proj_path)
    os.environ["PROJ_DATA"] = str(proj_path)

import geopandas as gpd
import osmnx as ox

# --------------------------------------------------
# 2. OSMnx settings
# --------------------------------------------------
ox.settings.use_cache = True
ox.settings.timeout = 300
ox.settings.overpass_url = "https://lz4.overpass-api.de/api"

# --------------------------------------------------
# 3. File paths
# --------------------------------------------------
data_dir = Path("data/processed")
data_dir.mkdir(parents=True, exist_ok=True)

run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

boundary_path = data_dir / f"koto_boundary_.gpkg"
output_path = data_dir / f"koto_walk_network_full_{run_id}.gpkg"

# --------------------------------------------------
# 4. Load existing Koto City boundary
# --------------------------------------------------
if not boundary_path.exists():
    raise FileNotFoundError(
        f"Boundary file not found: {boundary_path}. "
        "Run the drive network script first to create koto_boundary.gpkg."
    )

boundary_gdf = gpd.read_file(boundary_path)
koto_polygon = boundary_gdf.iloc[0].geometry

print("Loaded Koto boundary from:", boundary_path)

# --------------------------------------------------
# 5. Download walking network
# --------------------------------------------------
print("Downloading walking network for Koto City...")

G_walk = ox.graph_from_polygon(
    koto_polygon,
    network_type="walk",
    simplify=True,
    retain_all=True,
    truncate_by_edge=True,
)

print("Download complete.")
print("Nodes:", len(G_walk.nodes))
print("Edges:", len(G_walk.edges))

# --------------------------------------------------
# 6. Save walking network for QGIS
# --------------------------------------------------
ox.save_graph_geopackage(
    G_walk,
    filepath=str(output_path)
)

print("Saved walking network to:", output_path)
print("Finished successfully.")