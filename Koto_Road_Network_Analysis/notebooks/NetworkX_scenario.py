import os
import sys
from pathlib import Path

# Fix GDAL/PROJ paths if needed
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
import networkx as nx
import osmnx as ox

base_dir = Path("data/processed")

road_path = base_dir / "Road_network_full.gpkg"
impact_path = base_dir / "HeavyRain_impact.gpkg"

#print("Road file exists:", road_path.exists())
#print("Impact file exists:", impact_path.exists())

nodes = gpd.read_file(road_path, layer="nodes")
edges_impact = gpd.read_file(impact_path, layer="edges_flood_impact")

# Make sure nodes and edges use the same CRS
if nodes.crs != edges_impact.crs:
    nodes = nodes.to_crs(edges_impact.crs)

# Make sure node table has osmid
if "osmid" not in nodes.columns:
    nodes["osmid"] = nodes.index

# Set node index
nodes = nodes.set_index("osmid", drop=False)

# Update x and y coordinates from geometry
nodes["x"] = nodes.geometry.x
nodes["y"] = nodes.geometry.y

# Make sure u, v and key are numeric
for col in ["u", "v", "key"]:
    edges_impact[col] = pd.to_numeric(edges_impact[col], errors="coerce")

# Check if conversion worked
#print(edges_impact[["u", "v", "key"]].isna().sum())

# Convert to integer type, because u, v and key should be graph identifiers
edges_impact["u"] = edges_impact["u"].astype("int64")
edges_impact["v"] = edges_impact["v"].astype("int64")
edges_impact["key"] = edges_impact["key"].astype("int64")

# Set edge index
edges_impact = edges_impact.set_index(["u", "v", "key"], drop=True)

G_baseline = ox.graph_from_gdfs(nodes, edges_impact)

remove_classes = [
    "severe_disruption_likely_impassable",
    "high_risk_tunnel_or_underpass"
]

edges_available_heavyrain = edges_impact[
    ~edges_impact["disruption_class"].isin(remove_classes)
].copy()

edges_removed_heavyrain = edges_impact[
    edges_impact["disruption_class"].isin(remove_classes)
].copy()

#print("Original edges:", len(edges_impact))
#print("Available edges after flooding:", len(edges_available_heavyrain))
#print("Removed edges:", len(edges_removed_heavyrain))

#print("\nRemoved disruption classes:")
#print(edges_removed_heavyrain["disruption_class"].value_counts())

G_heavyrain = ox.graph_from_gdfs(nodes, edges_available_heavyrain)

#print("HeavyRain scenario graph created")
#print("Nodes:", G_heavyrain.number_of_nodes())
#print("Edges:", G_heavyrain.number_of_edges())

def total_edge_length_km(G):
    total_m = 0
    
    for u, v, key, data in G.edges(keys=True, data=True):
        length = data.get("length", 0)
        if pd.notna(length):
            total_m += float(length)
    
    return total_m / 1000


def network_metrics(G, scenario_name):
    G_undirected = G.to_undirected()
    
    components = list(nx.connected_components(G_undirected))
    component_sizes = [len(c) for c in components]
    
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    total_length_km = total_edge_length_km(G)
    
    largest_component_size = max(component_sizes) if component_sizes else 0
    isolated_nodes = nx.number_of_isolates(G_undirected)
    
    return {
        "scenario": scenario_name,
        "nodes": total_nodes,
        "edges": total_edges,
        "available_edge_length_km": total_length_km,
        "connected_components": len(components),
        "largest_component_nodes": largest_component_size,
        "largest_component_share_percent": largest_component_size / total_nodes * 100 if total_nodes > 0 else 0,
        "isolated_nodes": isolated_nodes
    }


baseline_metrics = network_metrics(G_baseline, "baseline")
heavyrain_metrics = network_metrics(G_heavyrain, "heavy_rain_flood")

metrics_df = pd.DataFrame([baseline_metrics, heavyrain_metrics])

baseline_length = metrics_df.loc[
    metrics_df["scenario"] == "baseline", 
    "available_edge_length_km"
].iloc[0]

heavyrain_length = metrics_df.loc[
    metrics_df["scenario"] == "heavy_rain_flood", 
    "available_edge_length_km"
].iloc[0]

road_length_lost_km = baseline_length - heavyrain_length
road_length_lost_percent = road_length_lost_km / baseline_length * 100

print(f"Road length lost: {road_length_lost_km:.2f} km")
print(f"Road length lost: {road_length_lost_percent:.2f}%")

output_dir = Path("outputs/tables")
output_dir.mkdir(parents=True, exist_ok=True)

metrics_df.to_csv(
    output_dir / "network_metrics_baseline_vs_heavyrain.csv",
    index=False
)

print("\nSaved network metrics to:")
print(output_dir / "network_metrics_baseline_vs_heavyrain.csv")

removed_summary = (
    edges_removed_heavyrain
    .groupby("disruption_class")
    .agg(
        removed_edges=("geometry", "count"),
        removed_length_m=("length", "sum")
    )
    .reset_index()
)

removed_summary["removed_length_km"] = removed_summary["removed_length_m"] / 1000
removed_summary["share_of_removed_length_percent"] = (
    removed_summary["removed_length_m"] / removed_summary["removed_length_m"].sum() * 100
)

print("\nRemoved edges by disruption class:")
print(removed_summary.to_string(index=False))

removed_summary.to_csv(
    output_dir / "removed_edges_by_disruption_class_heavyrain.csv",
    index=False
)

# --------------------------------------------------
# Export baseline and HeavyRain scenario layers for QGIS
# --------------------------------------------------

qgis_output_path = Path("data/processed/HeavyRain_road_network.gpkg")

# Convert indexed GeoDataFrames back to normal columns for QGIS export
baseline_edges_qgis = edges_impact.reset_index().copy()
available_edges_qgis = edges_available_heavyrain.reset_index().copy()
removed_edges_qgis = edges_removed_heavyrain.reset_index().copy()

# Export layers
#baseline_edges_qgis.to_file(
#    qgis_output_path,
#    layer="baseline_all_edges",
#    driver="GPKG"
#)

#available_edges_qgis.to_file(
#    qgis_output_path,
#    layer="heavyrain_available_edges",
#    driver="GPKG"
#)

#removed_edges_qgis.to_file(
#    qgis_output_path,
#    layer="heavyrain_removed_edges",
#    driver="GPKG"
#)

print("\nQGIS scenario layers saved to:")
print(qgis_output_path)
print("Layers:")
print("- baseline_all_edges")
print("- heavyrain_available_edges")
print("- heavyrain_removed_edges")