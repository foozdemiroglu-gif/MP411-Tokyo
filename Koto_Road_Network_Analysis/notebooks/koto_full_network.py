import os
import sys
from pathlib import Path
from datetime import datetime

import osmnx as ox

# --------------------------------------------------
# 1. Fix GDAL / PROJ paths automatically if possible
# --------------------------------------------------
env_path = Path(sys.prefix)

gdal_path = env_path / "Library" / "share" / "gdal"
proj_path = env_path / "Library" / "share" / "proj"

if gdal_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_path)

if proj_path.exists():
    os.environ["PROJ_LIB"] = str(proj_path)

# --------------------------------------------------
# 2. OSMnx settings
# --------------------------------------------------
ox.settings.use_cache = True
ox.settings.timeout = 300
ox.settings.overpass_url = "https://lz4.overpass-api.de/api"

# --------------------------------------------------
# 3. Output folder
# --------------------------------------------------
out_dir = Path("data/processed")
out_dir.mkdir(parents=True, exist_ok=True)

run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

# --------------------------------------------------
# 4. Find Koto City boundary
# --------------------------------------------------
queries = [
    "Koto-ku, Tokyo, Japan",
    "Kōtō-ku, Tokyo, Japan",
    "Koto City, Tokyo, Japan",
    "Kōtō City, Tokyo, Japan",
    "Koto Ward, Tokyo, Japan",
]

boundary_gdf = None
used_query = None

for query in queries:
    try:
        print(f"Trying boundary query: {query}")
        candidate = ox.geocode_to_gdf(query)

        if not candidate.empty:
            boundary_gdf = candidate
            used_query = query
            print(f"Using boundary query: {query}")
            break

    except Exception as e:
        print(f"Failed query '{query}': {e}")

if boundary_gdf is None or boundary_gdf.empty:
    raise RuntimeError("Could not find a usable boundary for Koto City.")

# --------------------------------------------------
# 5. Download full road network within Koto boundary
# --------------------------------------------------
koto_polygon = boundary_gdf.iloc[0].geometry

print("Downloading road network for Koto City...")

G = ox.graph_from_polygon(
    koto_polygon,
    network_type="drive",
    simplify=True,
    retain_all=True,
    truncate_by_edge=True,
)

print("Download complete.")
print("Nodes:", len(G.nodes))
print("Edges:", len(G.edges))


# --------------------------------------------------
# 6. Save graph as GeoPackage for QGIS
# --------------------------------------------------
output_path = out_dir / f"koto_drive_network_full_{run_id}.gpkg"

ox.save_graph_geopackage(
    G,
    filepath=str(output_path),
)

print("Saved road network to:", output_path)


# --------------------------------------------------
# 7. Also save the Koto boundary for QGIS
# --------------------------------------------------
boundary_path = out_dir / f"koto_boundary_{run_id}.gpkg"
boundary_gdf.to_file(boundary_path, driver="GPKG")

print("Saved Koto boundary to:", boundary_path)
print("Finished successfully.")