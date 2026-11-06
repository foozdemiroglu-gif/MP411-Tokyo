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

#------------------------------------------------
#Prepare nodes and edges for OSMnx graph conversion
#------------------------------------------------   

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

#------------------------------------------------
#Create baseline graph
#------------------------------------------------

G_baseline = ox.graph_from_gdfs(nodes, edges_impact)

#------------------------------------------------
#Create HeavyRain scenario graph
#------------------------------------------------

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


baseline_length_km = total_edge_length_km(G_baseline)
heavyrain_length_km = total_edge_length_km(G_heavyrain)

road_length_lost_km = baseline_length_km - heavyrain_length_km
road_length_lost_percent = road_length_lost_km / baseline_length_km * 100

print(f"Baseline road length: {baseline_length_km:.2f} km")
print(f"HeavyRain available road length: {heavyrain_length_km:.2f} km")
print(f"Road length lost: {road_length_lost_km:.2f} km")
print(f"Road length lost: {road_length_lost_percent:.2f}%")

# --------------------------------------------------
# Connectivity / fragmentation analysis
# --------------------------------------------------

def edge_length_km_for_component(G, component_nodes):
    total_m = 0
    
    for u, v, key, data in G.edges(keys=True, data=True):
        if u in component_nodes and v in component_nodes:
            length = data.get("length", 0)
            if pd.notna(length):
                total_m += float(length)
    
    return total_m / 1000


def component_analysis(G, scenario_name):
    # Convert to undirected graph for connectivity analysis
    G_undir = G.to_undirected()
    
    components = list(nx.connected_components(G_undir))
    components_sorted = sorted(components, key=len, reverse=True)
    
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    total_length_km = total_edge_length_km(G)
    
    rows = []
    node_to_component = {}
    
    for component_id, component_nodes in enumerate(components_sorted, start=1):
        component_nodes = set(component_nodes)
        
        for node in component_nodes:
            node_to_component[node] = component_id
        
        edge_count = 0
        for u, v, key in G.edges(keys=True):
            if u in component_nodes and v in component_nodes:
                edge_count += 1
        
        component_length_km = edge_length_km_for_component(G, component_nodes)
        
        rows.append({
            "scenario": scenario_name,
            "component_id": component_id,
            "node_count": len(component_nodes),
            "edge_count": edge_count,
            "edge_length_km": component_length_km,
            "node_share_percent": len(component_nodes) / total_nodes * 100 if total_nodes > 0 else 0,
            "edge_share_percent": edge_count / total_edges * 100 if total_edges > 0 else 0,
            "length_share_percent": component_length_km / total_length_km * 100 if total_length_km > 0 else 0
        })
    
    components_df = pd.DataFrame(rows)
    
    largest_component_nodes = components_df.loc[0, "node_count"] if len(components_df) > 0 else 0
    largest_component_length_km = components_df.loc[0, "edge_length_km"] if len(components_df) > 0 else 0
    
    summary = {
        "scenario": scenario_name,
        "nodes": total_nodes,
        "edges": total_edges,
        "total_edge_length_km": total_length_km,
        "connected_components": len(components_sorted),
        "largest_component_nodes": largest_component_nodes,
        "largest_component_node_share_percent": largest_component_nodes / total_nodes * 100 if total_nodes > 0 else 0,
        "largest_component_edge_length_km": largest_component_length_km,
        "largest_component_length_share_percent": largest_component_length_km / total_length_km * 100 if total_length_km > 0 else 0,
        "nodes_outside_largest_component": total_nodes - largest_component_nodes,
        "isolated_nodes": nx.number_of_isolates(G_undir)
    }
    
    return summary, components_df, node_to_component

# --------------------------------------------------
# Run component analysis
# --------------------------------------------------

baseline_summary, baseline_components, baseline_node_to_component = component_analysis(
    G_baseline,
    "baseline"
)

heavyrain_summary, heavyrain_components, heavyrain_node_to_component = component_analysis(
    G_heavyrain,
    "heavy_rain_flood"
)

connectivity_summary_df = pd.DataFrame([
    baseline_summary,
    heavyrain_summary
])

#print("\nConnectivity summary:")
#print(connectivity_summary_df.to_string(index=False))

#print("\nLargest HeavyRain components:")
#print(heavyrain_components.head(20).to_string(index=False))

# --------------------------------------------------
# Save connectivity results
# --------------------------------------------------

#output_dir = Path("outputs/tables")
#output_dir.mkdir(parents=True, exist_ok=True)

#connectivity_summary_df.to_csv(
#    output_dir / "connectivity_summary_baseline_vs_heavyrain.csv",
#    index=False
#)

#baseline_components.to_csv(
#    output_dir / "components_baseline.csv",
#    index=False
#)

#heavyrain_components.to_csv(
#    output_dir / "components_heavyrain.csv",
#    index=False
#)

#print("\nConnectivity tables saved to:")
#print(output_dir)

# --------------------------------------------------
# Export HeavyRain connected components for QGIS
# --------------------------------------------------

component_output_path = Path("data/processed/koto_heavyrain_network_components.gpkg")

# If the file already exists and is not open in QGIS, remove it first
if component_output_path.exists():
    component_output_path.unlink()

# --------------------------------------------------
# Helper: classify component size
# --------------------------------------------------

def classify_component(row):
    if row["component_id"] == 1:
        return "largest_component"
    elif row["component_node_count"] >= 20:
        return "medium_component"
    elif row["component_node_count"] > 1:
        return "small_component"
    else:
        return "isolated_node"

# --------------------------------------------------
# Prepare nodes with component IDs
# --------------------------------------------------

nodes_components_qgis = nodes.copy().reset_index(drop=True)

nodes_components_qgis["component_id"] = nodes_components_qgis["osmid"].map(
    heavyrain_node_to_component
)

component_size_map = heavyrain_components.set_index("component_id")["node_count"].to_dict()

nodes_components_qgis["component_node_count"] = nodes_components_qgis["component_id"].map(
    component_size_map
)

nodes_components_qgis["component_category"] = nodes_components_qgis.apply(
    classify_component,
    axis=1
)

# --------------------------------------------------
# Prepare available HeavyRain edges with component IDs
# --------------------------------------------------

heavyrain_edges_components_qgis = edges_available_heavyrain.reset_index().copy()

heavyrain_edges_components_qgis["component_id"] = heavyrain_edges_components_qgis["u"].map(
    heavyrain_node_to_component
)

heavyrain_edges_components_qgis["component_node_count"] = heavyrain_edges_components_qgis["component_id"].map(
    component_size_map
)

heavyrain_edges_components_qgis["component_category"] = heavyrain_edges_components_qgis.apply(
    classify_component,
    axis=1
)

# --------------------------------------------------
# Prepare removed edges as optional overlay
# --------------------------------------------------

removed_edges_qgis = edges_removed_heavyrain.reset_index().copy()
removed_edges_qgis["component_category"] = "removed_edge"

# --------------------------------------------------
# Export to GeoPackage
# --------------------------------------------------

heavyrain_edges_components_qgis.to_file(
    component_output_path,
    layer="heavyrain_edges_components",
    driver="GPKG"
)

nodes_components_qgis.to_file(
    component_output_path,
    layer="heavyrain_nodes_components",
    driver="GPKG"
)

removed_edges_qgis.to_file(
    component_output_path,
    layer="heavyrain_removed_edges",
    driver="GPKG"
)

print("\nHeavyRain component layers saved to:")
print(component_output_path)
print("Layers:")
print("- heavyrain_edges_components")
print("- heavyrain_nodes_components")
print("- heavyrain_removed_edges")