import os
import sys
from pathlib import Path

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
    os.environ["PROJ_DATA"] = str(proj_path)

# --------------------------------------------------
# 2. Import packages
# --------------------------------------------------
import pandas as pd
import geopandas as gpd

# --------------------------------------------------
# 3. Load CSV
# --------------------------------------------------
csv_path = "data/raw/shinsui_koutounaibu.csv"

df = pd.read_csv(csv_path, encoding="utf-8-sig")

print(df.head())
print(df.columns)

# --------------------------------------------------
# 4. Convert to GeoDataFrame
# --------------------------------------------------
gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
    crs="EPSG:4326"
)

# --------------------------------------------------
# 5. Save as GeoPackage
# --------------------------------------------------
output_path = "data/processed/flood_koutounaibu_points.gpkg"

gdf.to_file(
    output_path,
    layer="flood_depth_points",
    driver="GPKG"
)

print("Saved flood depth points to:", output_path)