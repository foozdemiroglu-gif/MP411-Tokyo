import os
import sys
from pathlib import Path

#--------------------------------------------------
# 1. Fix GDAL / import packages
#--------------------------------------------------
env_path = Path(sys.prefix)
gdal_path = env_path / "Library" / "share" / "gdal"
proj_path = env_path / "Library" / "share" / "proj"

if gdal_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_path)
if proj_path.exists():
    os.environ["PROJ_LIB"] = str(proj_path)
    os.environ["PROJ_DATA"] = str(proj_path)

import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
from shapely.geometry import LineString, MultiLineString

#--------------------------------------------------
# 2. Load road edges and flood raster
#--------------------------------------------------
base_dir = Path("data/processed")

roads_path = base_dir / "Koto_road_network_full.gpkg"
flood_raster_path = base_dir / "HeavyRain_koto_raster.tif"

edges = gpd.read_file(roads_path, layer="edges")

#print("Road edges loaded:", len(edges))
#print("Road CRS:", edges.crs)

#with rasterio.open(flood_raster_path) as src:
    #print("Flood raster CRS:", src.crs)
    #print("Flood raster resolution:", src.res)
    #print("Flood raster NoData:", src.nodata)

#--------------------------------------------------
# 3. Reproject roads to the raster CRS
#--------------------------------------------------
with rasterio.open(flood_raster_path) as src:
    raster_crs = src.crs

edges = edges.to_crs(raster_crs)

#print("Reprojected road CRS:", edges.crs)

#--------------------------------------------------
# 4. Keep only useful attributes
#--------------------------------------------------
keep_cols = [
    "u", "v", "key",
    "osmid",
    "highway",
    "bridge",
    "tunnel",
    "oneway",
    "name",
    "ref",
    "length",
    "maxspeed",
    "geometry"
]

available_cols = [col for col in keep_cols if col in edges.columns]
edges_work = edges[available_cols].copy()

#print("Columns kept:")
#print(edges_work.columns.tolist())

#--------------------------------------------------
# 5. Classify road structure
#--------------------------------------------------
def clean_value(value):
    if pd.isna(value):
        return ""
    return str(value).lower().strip()

def classify_road_structure(row):
    bridge = clean_value(row.get("bridge", ""))
    tunnel = clean_value(row.get("tunnel", ""))
    
    if tunnel not in ["", "no", "none", "nan", "false"]:
        return "tunnel_or_underpass"
    
    if bridge not in ["", "no", "none", "nan", "false"]:
        return "bridge_or_elevated_structure"
    
    return "at_grade_or_unknown"

edges_work["road_structure_class"] = edges_work.apply(classify_road_structure, axis=1)

#print(edges_work["road_structure_class"].value_counts())

#--------------------------------------------------
# 6. Classify road function
#--------------------------------------------------
def value_contains(value, options):
    value_str = str(value).lower()
    return any(option in value_str for option in options)

def classify_road_function(highway_value):
    highway_value = str(highway_value).lower()
    
    if value_contains(highway_value, ["motorway"]):
        return "highway"
    
    if value_contains(highway_value, ["trunk", "primary", "secondary"]):
        return "main_road"
    
    if value_contains(highway_value, ["tertiary", "residential", "unclassified", "service"]):
        return "local_road"
    
    return "other_or_unknown"

edges_work["road_function_class"] = edges_work["highway"].apply(classify_road_function)

#print(edges_work["road_function_class"].value_counts())

#--------------------------------------------------
# 7. Sample maximum flood depth per road segment
#--------------------------------------------------
def sample_points_along_line(geometry, spacing=10):
    """
    Creates points along a LineString or MultiLineString every 'spacing' metres.
    """
    points = []
    
    if geometry is None or geometry.is_empty:
        return points
    
    if isinstance(geometry, LineString):
        lines = [geometry]
    elif isinstance(geometry, MultiLineString):
        lines = list(geometry.geoms)
    else:
        return points
    
    for line in lines:
        length = line.length
        if length == 0:
            continue
        
        distances = np.arange(0, length + spacing, spacing)
        for distance in distances:
            if distance <= length:
                point = line.interpolate(distance)
                points.append((point.x, point.y))
    
    return points


def max_raster_value_along_geometry(geometry, raster_path, spacing=10):
    points = sample_points_along_line(geometry, spacing=spacing)
    
    if len(points) == 0:
        return np.nan
    
    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        values = []
        
        for value in src.sample(points):
            v = value[0]
            if nodata is not None and v == nodata:
                continue
            if np.isnan(v):
                continue
            values.append(v)
    
    if len(values) == 0:
        return 0.0
    
    return float(np.max(values))


edges_work["max_flood_depth_m"] = edges_work["geometry"].apply(
    lambda geom: max_raster_value_along_geometry(
        geom,
        flood_raster_path,
        spacing=10
    )
)

#print(edges_work["max_flood_depth_m"].describe())

#--------------------------------------------------
# 8. Classify disruption level
#--------------------------------------------------
def classify_disruption(row):
    depth = row["max_flood_depth_m"]
    structure = row["road_structure_class"]
    
    if pd.isna(depth):
        return "unknown"
    
    if structure == "bridge_or_elevated_structure":
        if depth >= 0.1:
            return "special_case_bridge_or_elevated"
        else:
            return "no_relevant_flooding"
    
    if structure == "tunnel_or_underpass":
        if depth >= 0.1:
            return "high_risk_tunnel_or_underpass"
        else:
            return "no_relevant_flooding"
    
    # At-grade or unknown roads
    if depth < 0.1:
        return "no_relevant_flooding"
    elif depth < 0.3:
        return "minor_disruption"
    elif depth < 0.5:
        return "reduced_accessibility"
    else:
        return "severe_disruption_likely_impassable"

edges_work["disruption_class"] = edges_work.apply(classify_disruption, axis=1)

#print(edges_work["disruption_class"].value_counts())

#--------------------------------------------------
# 9. Calculate summary statistics
#--------------------------------------------------

# Make sure the output folder exists
output_dir = Path("outputs/tables")
output_dir.mkdir(parents=True, exist_ok=True)

# Total road-network length
total_length_m = edges_work["length"].sum()
total_length_km = total_length_m / 1000

print("Total analysed road length:")
print(f"{total_length_km:.2f} km")


#--------------------------------------------------
# 9.1 Summary by disruption class
#--------------------------------------------------

summary_by_disruption = (
    edges_work
    .groupby("disruption_class")
    .agg(
        number_of_segments=("geometry", "count"),
        total_length_m=("length", "sum")
    )
    .reset_index()
)

summary_by_disruption["total_length_km"] = (
    summary_by_disruption["total_length_m"] / 1000
)

summary_by_disruption["percentage_of_total_length"] = (
    summary_by_disruption["total_length_m"] / total_length_m * 100
)

summary_by_disruption = summary_by_disruption.sort_values(
    "total_length_m",
    ascending=False
)

print("\nSummary by disruption class:")
print(summary_by_disruption)


#--------------------------------------------------
# 9.2 Summary by road function and disruption class
#--------------------------------------------------
summary_by_function = (
    edges_work
    .groupby(["road_function_class", "disruption_class"])
    .agg(
        number_of_segments=("geometry", "count"),
        total_length_m=("length", "sum")
    )
    .reset_index()
)

summary_by_function["total_length_km"] = (
    summary_by_function["total_length_m"] / 1000
)

summary_by_function["percentage_of_total_length"] = (
    summary_by_function["total_length_m"] / total_length_m * 100
)

summary_by_function = summary_by_function.sort_values(
    ["road_function_class", "total_length_m"],
    ascending=[True, False]
)

print("\nSummary by road function and disruption class:")
print(summary_by_function)


#--------------------------------------------------
# 9.3 Summary by road structure and disruption class
#--------------------------------------------------
summary_by_structure = (
    edges_work
    .groupby(["road_structure_class", "disruption_class"])
    .agg(
        number_of_segments=("geometry", "count"),
        total_length_m=("length", "sum")
    )
    .reset_index()
)

summary_by_structure["total_length_km"] = (
    summary_by_structure["total_length_m"] / 1000
)

summary_by_structure["percentage_of_total_length"] = (
    summary_by_structure["total_length_m"] / total_length_m * 100
)

summary_by_structure = summary_by_structure.sort_values(
    ["road_structure_class", "total_length_m"],
    ascending=[True, False]
)

print("\nSummary by road structure and disruption class:")
print(summary_by_structure)

#--------------------------------------------------
# 9.4 Summary of flooded versus non-flooded roads
#--------------------------------------------------
edges_work["is_relevantly_flooded"] = edges_work["max_flood_depth_m"] >= 0.1

summary_flooded_binary = (
    edges_work
    .groupby("is_relevantly_flooded")
    .agg(
        number_of_segments=("geometry", "count"),
        total_length_m=("length", "sum")
    )
    .reset_index()
)

summary_flooded_binary["total_length_km"] = (
    summary_flooded_binary["total_length_m"] / 1000
)

summary_flooded_binary["percentage_of_total_length"] = (
    summary_flooded_binary["total_length_m"] / total_length_m * 100
)

summary_flooded_binary["flood_status"] = summary_flooded_binary[
    "is_relevantly_flooded"
].map({
    True: "flooded_0_1m_or_more",
    False: "not_relevantly_flooded"
})

summary_flooded_binary = summary_flooded_binary[
    [
        "flood_status",
        "number_of_segments",
        "total_length_m",
        "total_length_km",
        "percentage_of_total_length"
    ]
]

print("\nSummary of flooded versus non-flooded roads:")
print(summary_flooded_binary)

#--------------------------------------------------
# 9.5 Save summary tables as CSV files
#--------------------------------------------------
summary_by_disruption.to_csv(
    output_dir / "summary_disruption_combined.csv",
    index=False
)

summary_by_function.to_csv(
    output_dir / "summary_by_road_function_combined.csv",
    index=False
)

summary_by_structure.to_csv(
    output_dir / "summary_by_road_structure_combined.csv",
    index=False
)

summary_flooded_binary.to_csv(
    output_dir / "summary_flooded_binary_combined.csv",
    index=False
)

print("\nSummary tables saved to:")
print(output_dir)

#--------------------------------------------------
#10. Save output for QGIS
#--------------------------------------------------
#output_path = base_dir / "koto_road_flood_impact.gpkg"

#edges_work.to_file(
#    output_path,
#    layer="edges_flood_impact",
#    driver="GPKG"
#)

#print("Saved:", output_path)