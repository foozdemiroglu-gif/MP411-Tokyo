from pathlib import Path
import pandas as pd

# Find the CSV whether the notebook runs from the project folder
# or from the notebooks folder.
csv_path = Path("data/raw/OD_koto_only.csv")
if not csv_path.exists():
    csv_path = Path("../data/raw/OD_koto_only.csv")

if not csv_path.exists():
    raise FileNotFoundError(f"Cannot find OD_koto_only.csv. Working folder: {Path.cwd()}")

# ============================================================
# 1. Clean OD codes
# ============================================================
od = pd.read_csv(
    csv_path,
    dtype={"origin_area": str, "destination_area": str}
)

# print("Before cleaning:")
# print(od[["origin_area", "destination_area"]].head())

# Remove surrounding spaces and the leading colon.
for column in ["origin_area", "destination_area"]:
    od[column] = od[column].str.strip().str.lstrip(":")

# print("\nAfter cleaning:")
# print(od[["origin_area", "destination_area"]].head())
# print("\nNumber of OD pairs:", len(od))
# print("Total car trips:", od["car_trips"].sum())

# ============================================================
# 2. Check for missing columns
# ============================================================
required_columns = {
    "origin_area",
    "destination_area",
    "car_trips",
    "Origin_node_osmid",
    "Destination_node_osmid",
}

missing = required_columns - set(od.columns)
assert not missing, f"Missing columns: {missing}"

# print("OD pairs:", len(od))
# print("Car trips:", pd.to_numeric(od["car_trips"]).sum())
# print("Missing node IDs:")
# print(od[["Origin_node_osmid", "Destination_node_osmid"]].isna().sum())
# print(od.head())

# ============================================================
# 3. Load and inspect the road network
# ============================================================
import geopandas as gpd

network_path = Path("data/processed/road_network/Road_network_full.gpkg")
if not network_path.exists():
    network_path = Path("../data/processed/road_network/Road_network_full.gpkg")

if not network_path.exists():
    raise FileNotFoundError(f"Cannot find Road_network_full.gpkg. Working folder: {Path.cwd()}")

nodes_gdf = gpd.read_file(network_path, layer="nodes")
edges_gdf = gpd.read_file(network_path, layer="edges")

# print("Nodes:", len(nodes_gdf))
# print("Edges:", len(edges_gdf))
# print("CRS:", edges_gdf.crs)
# print("\nRoad fields:")
# print(edges_gdf.columns.tolist())
# print("\nExample roads:")
# print(edges_gdf[["u", "v", "from", "to", "oneway", "length"]].head())

# ============================================================
# 4. Check one-way and two-way roads
# ============================================================
# print("One-way values:")
# print(edges_gdf["oneway"].value_counts(dropna=False))

# print("\nExamples of two-way roads:")
# print(
#     edges_gdf.loc[
#         edges_gdf["oneway"] == False,
#         ["u", "v", "from", "to", "length"]
#     ].head(3)
# )

# ============================================================
# 5. Build the directed road graph
# ============================================================
import networkx as nx

G = nx.MultiDiGraph()
G.add_nodes_from(nodes_gdf["osmid"].astype("int64"))

for edge_row, road in edges_gdf.iterrows():
    if road["oneway"]:
        directions = [(int(road["from"]), int(road["to"]))]
    else:
        directions = [
            (int(road["u"]), int(road["v"])),
            (int(road["v"]), int(road["u"])),
        ]

    for start, end in directions:
        G.add_edge(
            start,
            end,
            length=float(road["length"]),
            edge_row=int(edge_row),
        )

# print("Graph nodes:", G.number_of_nodes())
# print("Directed connections:", G.number_of_edges())

# ============================================================
# 6. Check that OD access nodes exist in the graph
# ============================================================
od_node_ids = (
    set(od["Origin_node_osmid"].astype(int))
    | set(od["Destination_node_osmid"].astype(int))
)
missing_nodes = od_node_ids - set(G.nodes)

if missing_nodes:
    raise ValueError(f"OD access nodes missing from graph: {missing_nodes}")

# ============================================================
# 7. Calculate all shortest-distance routes
# ============================================================
route_results = []
route_edge_parts = []

for _, trip in od.iterrows():
    origin_area = trip["origin_area"]
    destination_area = trip["destination_area"]
    start_node = int(trip["Origin_node_osmid"])
    end_node = int(trip["Destination_node_osmid"])
    car_trips = int(trip["car_trips"])
    route_id = f"{origin_area}_{destination_area}"

    try:
        path_nodes = nx.shortest_path(
            G, start_node, end_node, weight="length"
        )
    except nx.NetworkXNoPath as exc:
        raise ValueError(f"No route found for {route_id}") from exc

    # Find the original GeoPackage row for each connection.
    # Parallel connections between the same nodes are resolved
    # using the same minimum-length rule as the shortest path.
    edge_rows = []
    for from_node, to_node in zip(path_nodes[:-1], path_nodes[1:]):
        options = G.get_edge_data(from_node, to_node)
        chosen_key = min(
            options,
            key=lambda key: options[key]["length"]
        )
        edge_rows.append(options[chosen_key]["edge_row"])

    selected_edges = edges_gdf.loc[edge_rows].copy()
    route_length_m = selected_edges["length"].sum()

    # Keep each OD route separate, even when routes share a road.
    selected_edges["route_id"] = route_id
    selected_edges["origin_area"] = origin_area
    selected_edges["destination_area"] = destination_area
    selected_edges["car_trips"] = car_trips
    selected_edges["route_order"] = range(1, len(selected_edges) + 1)
    selected_edges["travel_from"] = path_nodes[:-1]
    selected_edges["travel_to"] = path_nodes[1:]
    route_edge_parts.append(selected_edges)

    route_results.append({
        "route_id": route_id,
        "origin_area": origin_area,
        "destination_area": destination_area,
        "car_trips": car_trips,
        "road_edges": len(edge_rows),
        "route_length_km": route_length_m / 1000,
        "node_path": "|".join(map(str, path_nodes)),
    })

routes_df = pd.DataFrame(route_results)
all_route_edges = gpd.GeoDataFrame(
    pd.concat(route_edge_parts, ignore_index=True),
    geometry=edges_gdf.geometry.name,
    crs=edges_gdf.crs,
)

# ============================================================
# 8. Check and save the results
# ============================================================
# assert len(routes_df) == len(od), "A route is missing."
# assert routes_df["car_trips"].sum() == od["car_trips"].sum()
# assert not all_route_edges.geometry.isna().any()

# output_dir = network_path.parent.parent / "OD_data"
# output_dir.mkdir(parents=True, exist_ok=True)

# routes_path = output_dir / "all_od_shortest_routes.gpkg"
# summary_path = output_dir / "all_od_route_summary.csv"

# all_route_edges.to_file(
#     routes_path,
#     layer="od_route_edges",
#     driver="GPKG",
# )
# routes_df.to_csv(summary_path, index=False)

# print("Routes calculated:", len(routes_df))
# print("Car trips represented:", routes_df["car_trips"].sum())
# print("Route-edge records saved:", len(all_route_edges))
# print("QGIS routes:", routes_path.resolve())
# print("Route summary:", summary_path.resolve())

# ============================================================
# 9. Aggregate assigned trips by directed road edge
# ============================================================
edge_flows = (
    all_route_edges
    .groupby(
        ["u", "v", "key", "travel_from", "travel_to"],
        as_index=False
    )
    .agg(
        assigned_car_trips=("car_trips", "sum"),
        od_pairs_using_edge=("route_id", "nunique"),
    )
)

# Each OD trip is counted once for every edge on its route.
expected_total = (
    routes_df["car_trips"] * routes_df["road_edges"]
).sum()
assert edge_flows["assigned_car_trips"].sum() == expected_total

# print("Directed road edges used:", len(edge_flows))
# print("Highest assigned trip count:", edge_flows["assigned_car_trips"].max())
# print("\nFive edges with the highest assigned counts:")
# print(
#     edge_flows.nlargest(5, "assigned_car_trips").to_string(index=False)
# )

# ============================================================
# 10. Create a road network layer with assigned trip totals
# ============================================================
road_keys = ["u", "v", "key"]

if edges_gdf.duplicated(road_keys).any():
    raise ValueError("Road keys are not unique; check before joining flows.")

road_totals = (
    all_route_edges
    .groupby(road_keys, as_index=False)
    .agg(
        assigned_car_trips=("car_trips", "sum"),
        od_pairs_using_edge=("route_id", "nunique"),
    )
)

roads_with_flows = edges_gdf.merge(
    road_totals,
    on=road_keys,
    how="left",
    validate="one_to_one",
)

# Roads that were not selected by any route receive zero.
for column in ["assigned_car_trips", "od_pairs_using_edge"]:
    roads_with_flows[column] = (
        roads_with_flows[column].fillna(0).astype(int)
    )

assert len(roads_with_flows) == len(edges_gdf)
assert (
    roads_with_flows["assigned_car_trips"].sum()
    == edge_flows["assigned_car_trips"].sum()
)

output_dir = network_path.parent.parent / "OD_data"
output_dir.mkdir(parents=True, exist_ok=True)
flow_map_path = output_dir / "od_assigned_road_flows.gpkg"
# roads_with_flows.to_file(
#     flow_map_path,
#     layer="road_assigned_flows",
#     driver="GPKG",
# )

# print("Road features:", len(roads_with_flows))
# print("Road features used by at least one OD route:",
#       (roads_with_flows["assigned_car_trips"] > 0).sum())
# print("Highest combined assigned count:",
#       roads_with_flows["assigned_car_trips"].max())
# print("Saved QGIS layer:", flow_map_path.resolve())

# ============================================================
# 11. Load and check roads available during heavy rainfall
# ============================================================

# CHANGE THIS PATH to your HeavyRain GeoPackage.
heavy_rain_path = Path(
    "data/processed/road_network/HeavyRain_road_network.gpkg"
)

available_edges = gpd.read_file(
    heavy_rain_path,
    layer="heavyrain_available_edges",
)

road_keys = ["u", "v", "key"]

for label, table in [
    ("Baseline roads", edges_gdf),
    ("Heavy-rain available roads", available_edges),
]:
    missing_columns = set(road_keys) - set(table.columns)

    if missing_columns:
        raise ValueError(
            f"{label}: missing columns {missing_columns}"
        )

    if table[road_keys].isna().any().any():
        raise ValueError(f"{label}: missing road identifiers.")

    if table.duplicated(road_keys).any():
        raise ValueError(f"{label}: duplicate road identifiers.")

baseline_ids = set(
    edges_gdf[road_keys].itertuples(index=False, name=None)
)

available_ids = set(
    available_edges[road_keys].itertuples(index=False, name=None)
)

unmatched_ids = available_ids - baseline_ids

if unmatched_ids:
    raise ValueError(
        f"{len(unmatched_ids)} available roads do not match "
        "the baseline network. Check that both layers come "
        "from the same original road network."
    )

# print("Baseline road features:", len(baseline_ids))
# print("Available during heavy rainfall:", len(available_ids))
# print("Excluded from this scenario:", len(baseline_ids - available_ids))
# print("All available road identifiers match the baseline.")

# ============================================================
# 12. Create the heavy-rain graph and check OD connectivity
# ============================================================

# Connect each baseline row to its original road identifiers.
if not edges_gdf.index.is_unique:
    raise ValueError("Baseline road row index is not unique.")

row_to_road_id = dict(
    zip(
        edges_gdf.index,
        edges_gdf[road_keys].itertuples(index=False, name=None),
    )
)

# Work on a copy: G remains our baseline graph.
G_heavy_rain = G.copy()

connections_to_remove = []
retained_road_ids = set()

for start, end, graph_key, attributes in G.edges(
    keys=True, data=True
):
    if "edge_row" not in attributes:
        raise ValueError(
            "A graph connection is missing its edge_row identifier."
        )

    edge_row = attributes["edge_row"]

    if edge_row not in row_to_road_id:
        raise ValueError(
            f"Graph edge_row {edge_row} is absent from edges_gdf."
        )

    road_id = row_to_road_id[edge_row]

    if road_id in available_ids:
        retained_road_ids.add(road_id)
    else:
        connections_to_remove.append((start, end, graph_key))

if retained_road_ids != available_ids:
    raise ValueError(
        "Some available road features are absent from the baseline graph."
    )

G_heavy_rain.remove_edges_from(connections_to_remove)

# Keep all nodes, including any that become isolated.
assert set(G_heavy_rain.nodes) == set(G.nodes)
assert (
    G_heavy_rain.number_of_edges()
    + len(connections_to_remove)
    == G.number_of_edges()
)

# print("Baseline directed connections:", G.number_of_edges())
# print("Heavy-rain directed connections:",
#       G_heavy_rain.number_of_edges())
# print("Directed connections removed:", len(connections_to_remove))
# print("Available road features retained:", len(retained_road_ids))

# Check every original OD pair without dropping disconnected trips.
connectivity_results = []

for _, trip in od.iterrows():
    origin_node = int(trip["Origin_node_osmid"])
    destination_node = int(trip["Destination_node_osmid"])

    if (
        origin_node not in G_heavy_rain
        or destination_node not in G_heavy_rain
    ):
        raise ValueError("An OD access node is missing from the graph.")

    connectivity_results.append({
        "origin_area": trip["origin_area"],
        "destination_area": trip["destination_area"],
        "car_trips": trip["car_trips"],
        "reachable": nx.has_path(
            G_heavy_rain, origin_node, destination_node
        ),
    })

od_connectivity = pd.DataFrame(connectivity_results)

reachable = od_connectivity["reachable"]
disconnected_pairs = od_connectivity.loc[~reachable].copy()

# print("\nReachable OD pairs:", reachable.sum(),
#       "out of", len(od_connectivity))
# print("Disconnected OD pairs:", len(disconnected_pairs))
# print("Car person trips with a route:",
#       od_connectivity.loc[reachable, "car_trips"].sum())
# print("Car person trips without a route:",
#       disconnected_pairs["car_trips"].sum())

# if not disconnected_pairs.empty:
#     print("\nDisconnected OD pairs:")
#     print(
#         disconnected_pairs[
#             ["origin_area", "destination_area", "car_trips"]
#         ].to_string(index=False)
#     )

# ============================================================
# 13. Check road connections at each zone access node
# ============================================================

# Collect the zone-node mappings from origins and destinations.
zone_nodes = pd.concat(
    [
        od[["origin_area", "Origin_node_osmid"]].rename(
            columns={
                "origin_area": "zone",
                "Origin_node_osmid": "node_id",
            }
        ),
        od[["destination_area", "Destination_node_osmid"]].rename(
            columns={
                "destination_area": "zone",
                "Destination_node_osmid": "node_id",
            }
        ),
    ],
    ignore_index=True,
).drop_duplicates()

if zone_nodes.groupby("zone")["node_id"].nunique().gt(1).any():
    raise ValueError("A zone has more than one assigned access node.")

node_checks = []

for _, row in zone_nodes.sort_values("zone").iterrows():
    node = int(row["node_id"])

    incoming = G_heavy_rain.in_degree(node)
    outgoing = G_heavy_rain.out_degree(node)

    if incoming == 0 and outgoing == 0:
        status = "ISOLATED"
    elif outgoing == 0:
        status = "NO EXIT"
    elif incoming == 0:
        status = "NO ENTRY"
    else:
        status = "Has entry and exit"

    node_checks.append({
        "zone": row["zone"],
        "node_id": node,
        "baseline_in": G.in_degree(node),
        "baseline_out": G.out_degree(node),
        "heavy_rain_in": incoming,
        "heavy_rain_out": outgoing,
        "status": status,
    })

access_node_check = pd.DataFrame(node_checks)

# print(access_node_check.to_string(index=False))

# ============================================================
# 14. Calculate heavy-rain OD shortest-distance routes
# ============================================================

heavy_rain_route_results = []
heavy_rain_route_edge_parts = []

for _, trip in od.iterrows():

    origin_area = trip["origin_area"]
    destination_area = trip["destination_area"]
    start_node = int(trip["Origin_node_osmid"])
    end_node = int(trip["Destination_node_osmid"])
    car_trips = int(trip["car_trips"])

    route_id = f"{origin_area}_{destination_area}"

    # Keep disconnected OD pairs out of the route assignment.
    if not nx.has_path(G_heavy_rain, start_node, end_node):
        continue

    # Calculate shortest-distance route in the disrupted network.
    path_nodes = nx.shortest_path(
        G_heavy_rain,
        start_node,
        end_node,
        weight="length"
    )

    edge_rows = []

    for from_node, to_node in zip(
        path_nodes[:-1], path_nodes[1:]
    ):

        options = G_heavy_rain.get_edge_data(
            from_node, to_node
        )

        chosen_key = min(
            options,
            key=lambda key: options[key]["length"]
        )

        edge_rows.append(
            options[chosen_key]["edge_row"]
        )

    # Retrieve the original road features.
    selected_edges = edges_gdf.loc[edge_rows].copy()

    route_length_m = selected_edges["length"].sum()

    # Check that the route only uses available roads.
    selected_road_ids = set(
        selected_edges[["u", "v", "key"]]
        .itertuples(index=False, name=None)
    )

    assert selected_road_ids.issubset(available_ids), (
        f"Route {route_id} uses a removed road."
    )

    # Preserve route and travel-direction information.
    selected_edges["route_id"] = route_id
    selected_edges["origin_area"] = origin_area
    selected_edges["destination_area"] = destination_area
    selected_edges["car_trips"] = car_trips
    selected_edges["route_order"] = range(
        1, len(selected_edges) + 1)
    selected_edges["travel_from"] = path_nodes[:-1]
    selected_edges["travel_to"] = path_nodes[1:]

    heavy_rain_route_edge_parts.append(selected_edges)

    heavy_rain_route_results.append({
        "route_id": route_id,
        "origin_area": origin_area,
        "destination_area": destination_area,
        "car_trips": car_trips,
        "road_edges": len(edge_rows),
        "route_length_km": route_length_m / 1000,
        "node_path": "|".join(map(str, path_nodes))
    })

heavy_rain_routes_df = pd.DataFrame(
    heavy_rain_route_results
)

heavy_rain_route_edges = gpd.GeoDataFrame(
    pd.concat(
        heavy_rain_route_edge_parts,
        ignore_index=True
    ),
    geometry=edges_gdf.geometry.name,
    crs=edges_gdf.crs
)

# ============================================================
# Validation checks
# ============================================================

expected_reachable = int(od_connectivity["reachable"].sum())

expected_trips = int(
    od_connectivity.loc[
        od_connectivity["reachable"], "car_trips"
    ].sum()
)

assert len(heavy_rain_routes_df) == expected_reachable

assert (
    heavy_rain_routes_df["car_trips"].sum()
    == expected_trips
)

assert not heavy_rain_route_edges.geometry.isna().any()

# print("\n=== HEAVY-RAIN OD ROUTING RESULTS ===")

# print("Routes calculated:", len(heavy_rain_routes_df))

# print(
#     "Car person trips represented:",
#     heavy_rain_routes_df["car_trips"].sum()
# )

# print(
#     "Mean route length (km):",
#     round(heavy_rain_routes_df["route_length_km"].mean(), 3)
# )

# print(
#     "Shortest route (km):",
#     round(heavy_rain_routes_df["route_length_km"].min(), 3)
# )

# print(
#     "Longest route (km):",
#     round(heavy_rain_routes_df["route_length_km"].max(), 3)
# )

# print("\nIndividual heavy-rain routes:")

# print(
#     heavy_rain_routes_df[
#         [
#             "origin_area",
#             "destination_area",
#             "car_trips",
#             "route_length_km"
#         ]
#     ].to_string(index=False)
# )


# ============================================================
# 15. Compare baseline and heavy-rain OD route distances
# ============================================================

# Compare only the OD pairs that remain reachable during heavy rain.
route_comparison = heavy_rain_routes_df[
    [
        "route_id",
        "origin_area",
        "destination_area",
        "car_trips",
        "route_length_km"
    ]
].merge(
    routes_df[["route_id", "route_length_km"]],
    on="route_id",
    how="left",
    validate="one_to_one",
    suffixes=("_heavy_rain", "_baseline")
)

# Check that all heavy-rain routes have a baseline counterpart.
assert len(route_comparison) == len(heavy_rain_routes_df)

assert route_comparison["route_length_km_baseline"].notna().all()

# Calculate additional travel distance.
route_comparison["additional_distance_km"] = (
    route_comparison["route_length_km_heavy_rain"]
    - route_comparison["route_length_km_baseline"]
)

# Calculate percentage detour relative to the baseline route.
route_comparison["detour_percent"] = (
    route_comparison["additional_distance_km"]
    / route_comparison["route_length_km_baseline"]
    * 100
)

# The heavy-rain graph is a subset of the baseline graph.
# Therefore, shortest-distance routes cannot become shorter.
tolerance = 1e-6

assert (
    route_comparison["additional_distance_km"] >= -tolerance
).all(), "A heavy-rain route is shorter than its baseline route."

# Avoid insignificant floating-point differences.
route_comparison.loc[
    route_comparison["additional_distance_km"].abs() < tolerance,
    "additional_distance_km"
] = 0.0

route_comparison.loc[
    route_comparison["additional_distance_km"] == 0,
    "detour_percent"
] = 0.0

# ============================================================
# Summary indicators
# ============================================================

total_trips = route_comparison["car_trips"].sum()

mean_baseline_km = route_comparison[
    "route_length_km_baseline"
].mean()

mean_heavy_rain_km = route_comparison[
    "route_length_km_heavy_rain"
].mean()

mean_additional_km = route_comparison[
    "additional_distance_km"
].mean()

# Weight distances by the OD demand represented by each route.
weighted_baseline_km = (
    (
        route_comparison["route_length_km_baseline"]
        * route_comparison["car_trips"]
    ).sum()
    / total_trips
)

weighted_heavy_rain_km = (
    (
        route_comparison["route_length_km_heavy_rain"]
        * route_comparison["car_trips"]
    ).sum()
    / total_trips
)

weighted_additional_km = (
    (
        route_comparison["additional_distance_km"]
        * route_comparison["car_trips"]
    ).sum()
    / total_trips
)

weighted_detour_percent = (
    weighted_additional_km
    / weighted_baseline_km
    * 100
)

# ============================================================
# Display results
# ============================================================

# print("\n=== BASELINE VS HEAVY-RAIN ROUTE COMPARISON ===")

# print("OD pairs compared:", len(route_comparison))
# print("Car person trips represented:", total_trips)

# print(
#     "OD pairs requiring a detour:",
#     (route_comparison["additional_distance_km"] > tolerance).sum()
# )

# print("\nUnweighted route distances:")
# print("Mean baseline distance (km):", round(mean_baseline_km, 3))
# print("Mean heavy-rain distance (km):", round(mean_heavy_rain_km, 3))
# print("Mean additional distance (km):", round(mean_additional_km, 3))

# print("\nDemand-weighted route distances:")
# print("Baseline (km):", round(weighted_baseline_km, 3))
# print("Heavy rain (km):", round(weighted_heavy_rain_km, 3))
# print("Additional distance (km):", round(weighted_additional_km, 3))
# print("Aggregate demand-weighted distance increase (%):",
#       round(weighted_detour_percent, 2))

# print("\nIndividual OD route comparisons:")

# print(
#     route_comparison[
#         [
#             "origin_area",
#             "destination_area",
#             "car_trips",
#             "route_length_km_baseline",
#             "route_length_km_heavy_rain",
#             "additional_distance_km",
#             "detour_percent"
#         ]
#     ]
#     .sort_values("additional_distance_km", ascending=False)
#     .round(3)
#     .to_string(index=False)
# )


# ============================================================
# 16. Export heavy-rain OD routes for QGIS validation
# ============================================================

# # Use the existing OD output folder.
# output_dir = network_path.parent.parent / "OD_data"
# output_dir.mkdir(parents=True, exist_ok=True)

# # Define output file.
# heavy_rain_routes_path = (
#     output_dir / "heavy_rain_od_routes.gpkg"
# )

# # Export the road segments used by the reachable OD routes.
# heavy_rain_route_edges.to_file(
#     heavy_rain_routes_path,
#     layer="heavy_rain_route_edges",
#     driver="GPKG"
# )

# print("\n=== HEAVY-RAIN ROUTE EXPORT ===")
# print("Exported OD routes:", heavy_rain_routes_df["route_id"].nunique())
# print("Exported route-edge records:", len(heavy_rain_route_edges))
# print("Output file:", heavy_rain_routes_path.resolve())


# ============================================================
# 17. Aggregate heavy-rain assigned road demand
# ============================================================

# 1. Aggregate demand by directed road connection.
# Keep the travel direction to distinguish opposite flows.

heavy_rain_edge_flows = (
    heavy_rain_route_edges
    .groupby(
        ["u", "v", "key", "travel_from", "travel_to"],
        as_index=False
    )
    .agg(
        assigned_car_trips=("car_trips", "sum"),
        od_pairs_using_edge=("route_id", "nunique")
    )
)

# Check that directed totals account for every route segment.
expected_total = (
    heavy_rain_routes_df["car_trips"]
    * heavy_rain_routes_df["road_edges"]
).sum()

assert (
    heavy_rain_edge_flows["assigned_car_trips"].sum()
    == expected_total
), "Directed flow totals do not match route assignments."


# 2. Aggregate demand per physical road feature.
# Combine both travel directions, just as in the baseline.

road_keys = ["u", "v", "key"]

heavy_rain_road_totals = (
    heavy_rain_route_edges
    .groupby(road_keys, as_index=False)
    .agg(
        assigned_car_trips=("car_trips", "sum"),
        od_pairs_using_edge=("route_id", "nunique")
    )
)


# 3. Attach assigned demand to all available heavy-rain roads.
# Roads not used by any OD route receive zero.

if available_edges.duplicated(road_keys).any():
    raise ValueError(
        "Heavy-rain available road identifiers are not unique."
    )

heavy_rain_roads_with_flows = available_edges.merge(
    heavy_rain_road_totals,
    on=road_keys,
    how="left",
    validate="one_to_one"
)

for column in ["assigned_car_trips", "od_pairs_using_edge"]:
    heavy_rain_roads_with_flows[column] = (
        heavy_rain_roads_with_flows[column]
        .fillna(0)
        .astype(int)
    )


# ============================================================
# Validation checks
# ============================================================

# All available roads must remain in the output.
assert len(heavy_rain_roads_with_flows) == len(available_edges)

# Assigned totals must agree between directional and physical roads.
assert (
    heavy_rain_roads_with_flows["assigned_car_trips"].sum()
    == heavy_rain_edge_flows["assigned_car_trips"].sum()
)

# Every assigned road must belong to the available network.
assigned_ids = set(
    heavy_rain_road_totals[road_keys]
    .itertuples(index=False, name=None)
)

assert assigned_ids.issubset(available_ids)

# No road should have negative assigned demand.
assert (
    heavy_rain_roads_with_flows["assigned_car_trips"] >= 0
).all()


# ============================================================
# Display results
# ============================================================

# roads_used = int(
#     (heavy_rain_roads_with_flows["assigned_car_trips"] > 0).sum()
# )

# print("\n=== HEAVY-RAIN ASSIGNED ROAD FLOWS ===")

# print("Reachable OD pairs:", len(heavy_rain_routes_df))

# print(
#     "Car person trips represented:",
#     heavy_rain_routes_df["car_trips"].sum()
# )

# print("Available road features:", len(heavy_rain_roads_with_flows))

# print("Road features used by OD routes:", roads_used)

# print(
#     "Road features with zero assigned demand:",
#     len(heavy_rain_roads_with_flows) - roads_used
# )

# print(
#     "Directed road connections used:",
#     len(heavy_rain_edge_flows)
# )

# print(
#     "Highest directional assigned demand:",
#     heavy_rain_edge_flows["assigned_car_trips"].max()
# )

# print(
#     "Highest combined assigned demand:",
#     heavy_rain_roads_with_flows["assigned_car_trips"].max()
# )

# print("\nTop 10 roads by combined assigned demand:")

# print(
#     heavy_rain_roads_with_flows[
#         [
#             "u", "v", "key",
#             "assigned_car_trips",
#             "od_pairs_using_edge"
#         ]
#     ]
#     .nlargest(10, "assigned_car_trips")
#     .to_string(index=False)
# )


# ============================================================
# 18. Export heavy-rain assigned road flows for QGIS
# ============================================================

# # Use the existing OD output folder.
# output_dir = network_path.parent.parent / "OD_data"
# output_dir.mkdir(parents=True, exist_ok=True)

# # Define output file.
# heavy_rain_flow_path = (
#     output_dir / "heavy_rain_assigned_road_flows.gpkg"
# )

# # Export all available heavy-rain road features,
# # including roads with zero assigned demand.
# heavy_rain_roads_with_flows.to_file(
#     heavy_rain_flow_path,
#     layer="heavy_rain_assigned_flows",
#     driver="GPKG"
# )

# print("\n=== HEAVY-RAIN FLOW EXPORT ===")
# print("Exported road features:", len(heavy_rain_roads_with_flows))
# print("Roads carrying assigned demand:",
#       (heavy_rain_roads_with_flows["assigned_car_trips"] > 0).sum())
# print("Output file:", heavy_rain_flow_path.resolve())


# ============================================================
# 19. Compare baseline and heavy-rain flows
#     for the same 13 reachable OD pairs
# ============================================================

road_keys = ["u", "v", "key"]

# 1. Identify the OD pairs that remain reachable.
reachable_route_ids = set(heavy_rain_routes_df["route_id"])

assert len(reachable_route_ids) == 13

# 2. Select their ORIGINAL baseline routes.
baseline_13_routes = routes_df[
    routes_df["route_id"].isin(reachable_route_ids)
].copy()

baseline_13_edges = all_route_edges[
    all_route_edges["route_id"].isin(reachable_route_ids)
].copy()

# Check that both scenarios represent exactly the same demand.
assert set(baseline_13_routes["route_id"]) == reachable_route_ids

demand_check = baseline_13_routes[
    ["route_id", "car_trips"]
].merge(
    heavy_rain_routes_df[["route_id", "car_trips"]],
    on="route_id",
    suffixes=("_baseline", "_heavy_rain"),
    validate="one_to_one"
)

assert (
    demand_check["car_trips_baseline"]
    == demand_check["car_trips_heavy_rain"]
).all()

assert baseline_13_routes["car_trips"].sum() == 8639
assert heavy_rain_routes_df["car_trips"].sum() == 8639


# 3. Aggregate baseline flows for ONLY these 13 OD pairs.
baseline_13_flows = (
    baseline_13_edges
    .groupby(road_keys, as_index=False)
    .agg(baseline_flow=("car_trips", "sum"))
)

# 4. Aggregate heavy-rain flows for the same OD pairs.
heavy_rain_13_flows = (
    heavy_rain_route_edges
    .groupby(road_keys, as_index=False)
    .agg(heavy_rain_flow=("car_trips", "sum"))
)


# 5. Start with the COMPLETE baseline road network.
# This also captures roads that were removed by flooding.
flow_comparison_13 = edges_gdf.copy()

flow_comparison_13 = flow_comparison_13.merge(
    baseline_13_flows,
    on=road_keys,
    how="left",
    validate="one_to_one"
)

flow_comparison_13 = flow_comparison_13.merge(
    heavy_rain_13_flows,
    on=road_keys,
    how="left",
    validate="one_to_one"
)

for column in ["baseline_flow", "heavy_rain_flow"]:
    flow_comparison_13[column] = (
        flow_comparison_13[column].fillna(0).astype(int)
    )


# 6. Calculate the change in assigned demand.
flow_comparison_13["flow_change"] = (
    flow_comparison_13["heavy_rain_flow"]
    - flow_comparison_13["baseline_flow"]
)

# Mark whether the road survives in the heavy-rain network.
flow_comparison_13["road_available"] = [
    road_id in available_ids
    for road_id in flow_comparison_13[
        road_keys
    ].itertuples(index=False, name=None)
]


# ============================================================
# Validation
# ============================================================

assert len(flow_comparison_13) == len(edges_gdf)

assert (
    flow_comparison_13["baseline_flow"].sum()
    == baseline_13_edges["car_trips"].sum()
)

assert (
    flow_comparison_13["heavy_rain_flow"].sum()
    == heavy_rain_route_edges["car_trips"].sum()
)

assert (
    flow_comparison_13.loc[
        ~flow_comparison_13["road_available"],
        "heavy_rain_flow"
    ] == 0
).all()

assert (
    flow_comparison_13["flow_change"].sum()
    == (
        flow_comparison_13["heavy_rain_flow"].sum()
        - flow_comparison_13["baseline_flow"].sum()
    )
)


# ============================================================
# Display results
# ============================================================

# print("\n=== LIKE-FOR-LIKE ROAD FLOW COMPARISON ===")

# print("OD pairs compared:", len(reachable_route_ids))
# print("Car person trips in each scenario:", 8639)

# print("\nBaseline roads used:",
#       (flow_comparison_13["baseline_flow"] > 0).sum())

# print("Heavy-rain roads used:",
#       (flow_comparison_13["heavy_rain_flow"] > 0).sum())

# # Focus on roads that remain available.
# retained_comparison = flow_comparison_13[
#     flow_comparison_13["road_available"]
# ].copy()

# print("\n=== CHANGES ON RETAINED ROADS ===")

# print("Roads with increased assigned demand:",
#       (retained_comparison["flow_change"] > 0).sum())

# print("Roads with decreased assigned demand:",
#       (retained_comparison["flow_change"] < 0).sum())

# print("Roads with unchanged assigned demand:",
#       (retained_comparison["flow_change"] == 0).sum())

# print("\nLargest increase:",
#       retained_comparison["flow_change"].max())

# print("Largest decrease:",
#       retained_comparison["flow_change"].min())

# print("\nTop 10 roads gaining assigned demand:")

# print(
#     retained_comparison.nlargest(10, "flow_change")[
#         road_keys
#         + ["baseline_flow", "heavy_rain_flow", "flow_change"]
#     ].to_string(index=False)
# )

# print("\nTop 10 retained roads losing assigned demand:")

# print(
#     retained_comparison.nsmallest(10, "flow_change")[
#         road_keys
#         + ["baseline_flow", "heavy_rain_flow", "flow_change"]
#     ].to_string(index=False)
# )

# # Separately report roads removed by flooding.
# removed_comparison = flow_comparison_13[
#     ~flow_comparison_13["road_available"]
# ]

# print("\n=== REMOVED ROADS ===")

# print("Removed roads used by these OD pairs in baseline:",
#       (removed_comparison["baseline_flow"] > 0).sum())


# ============================================================
# 20. Export like-for-like road-flow comparison for QGIS
# ============================================================

# # Use the existing OD output directory.
# output_dir = network_path.parent.parent / "OD_data"
# output_dir.mkdir(parents=True, exist_ok=True)

# # Define output file.
# flow_change_path = (
#     output_dir / "heavy_rain_flow_changes.gpkg"
# )

# # Create a separate export layer.
# flow_change_export = flow_comparison_13.copy()

# # Add a descriptive category for QGIS visualization.
# def classify_flow_change(row):
#     if not row["road_available"]:
#         return "Removed road"
#     elif row["flow_change"] > 0:
#         return "Increased demand"
#     elif row["flow_change"] < 0:
#         return "Decreased demand"
#     else:
#         return "Unchanged demand"


# flow_change_export["change_category"] = (
#     flow_change_export.apply(classify_flow_change, axis=1)
# )

# # Calculate absolute change for graduated line widths.
# flow_change_export["absolute_change"] = (
#     flow_change_export["flow_change"].abs()
# )

# # Export all baseline road features.
# flow_change_export.to_file(
#     flow_change_path,
#     layer="flow_changes_13_od_pairs",
#     driver="GPKG"
# )

# # ============================================================
# # Check export
# # ============================================================

# print("\n=== FLOW CHANGE EXPORT ===")
# print("Total road features:", len(flow_change_export))

# print("\nCategories:")
# print(flow_change_export["change_category"].value_counts())

# print("\nMaximum absolute change:",
#       flow_change_export["absolute_change"].max())

# print("\nOutput file:", flow_change_path.resolve())


# ============================================================
# 21. Check flood-exposure data for all baseline roads
# ============================================================

# Load roads removed under the Heavy Rain scenario.
removed_edges = gpd.read_file(
    heavy_rain_path,
    layer="heavyrain_removed_edges"
)

# Combine retained and removed road features.
flood_exposure_roads = gpd.GeoDataFrame(
    pd.concat(
        [available_edges, removed_edges],
        ignore_index=True
    ),
    geometry="geometry",
    crs=available_edges.crs
)

road_keys = ["u", "v", "key"]

# Check that every baseline road occurs exactly once.
assert len(flood_exposure_roads) == len(edges_gdf)

assert not flood_exposure_roads.duplicated(
    road_keys
).any()

exposure_ids = set(
    flood_exposure_roads[road_keys]
    .itertuples(index=False, name=None)
)

assert exposure_ids == baseline_ids

# # Display available flood-exposure attributes.
# print("\n=== FLOOD EXPOSURE DATA CHECK ===")

# print("Baseline roads:", len(edges_gdf))
# print("Retained roads:", len(available_edges))
# print("Removed roads:", len(removed_edges))
# print("Combined roads:", len(flood_exposure_roads))

# print("\nAvailable flood-exposure columns:")
# print(flood_exposure_roads.columns.tolist())

# # Examine flood-depth values.
# if "max_flood_depth_m" in flood_exposure_roads.columns:
#     print("\nFlood-depth summary (m):")
#     print(
#         flood_exposure_roads["max_flood_depth_m"]
#         .describe()
#     )

#     print(
#         "\nMissing flood-depth values:",
#         flood_exposure_roads["max_flood_depth_m"]
#         .isna().sum()
#     )

# if "disruption_class" in flood_exposure_roads.columns:
#     print("\nDisruption classes:")
#     print(
#         flood_exposure_roads["disruption_class"]
#         .value_counts(dropna=False)
#     )


# ============================================================
# 22. Combine flood exposure and OD-based road importance
# ============================================================

road_keys = ["u", "v", "key"]

# Select only the attributes needed from flood-exposure data.
exposure_columns = road_keys + [
    "max_flood_depth_m",
    "disruption_class",
    "road_structure_class",
    "road_function_class"
]

# Merge exposure information with the baseline OD flows.
vulnerability_importance = roads_with_flows.merge(
    flood_exposure_roads[exposure_columns],
    on=road_keys,
    how="left",
    validate="one_to_one",
    suffixes=("", "_flood")
)

# Confirm that all roads were matched.
assert len(vulnerability_importance) == 6352

assert vulnerability_importance[
    "max_flood_depth_m"
].notna().all()

assert vulnerability_importance[
    "assigned_car_trips"
].notna().all()

# Confirm that the original OD assignment is unchanged.
assert (
    vulnerability_importance["assigned_car_trips"].sum()
    == roads_with_flows["assigned_car_trips"].sum()
)

# Display summary statistics.
# print("\n=== VULNERABILITY–IMPORTANCE DATASET ===")

# print("Road features:", len(vulnerability_importance))

# print("\nAssigned OD demand:")
# print(
#     vulnerability_importance["assigned_car_trips"].describe()
# )

# print("\nRoads carrying assigned demand:",
#       (vulnerability_importance["assigned_car_trips"] > 0).sum())

# print("\nFlood exposure:")
# print(
#     vulnerability_importance["max_flood_depth_m"].describe()
# )

# print("\nRoad structure classes:")
# print(
#     vulnerability_importance["road_structure_class"]
#     .value_counts(dropna=False)
# )

# print("\nTop 10 roads by baseline assigned demand:")
# print(
#     vulnerability_importance.nlargest(
#         10, "assigned_car_trips"
#     )[
#         road_keys
#         + [
#             "assigned_car_trips",
#             "max_flood_depth_m",
#             "disruption_class",
#             "road_structure_class"
#         ]
#     ].to_string(index=False)
# )

# ============================================================
# 23. Examine flood exposure and OD-based importance
# ============================================================

# Roads used by at least one baseline OD route.
used_roads = vulnerability_importance[
    vulnerability_importance["assigned_car_trips"] > 0
].copy()

# Roads without a bridge/tunnel special classification.
at_grade_roads = vulnerability_importance[
    vulnerability_importance["road_structure_class"]
    == "at_grade_or_unknown"
].copy()

# print("\n=== OD DEMAND DISTRIBUTION (USED ROADS ONLY) ===")

# print(
#     used_roads["assigned_car_trips"].quantile(
#         [0, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.00]
#     )
# )

# print("\n=== FLOOD DEPTH DISTRIBUTION (ALL ROADS) ===")

# print(
#     vulnerability_importance["max_flood_depth_m"].quantile(
#         [0, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.00]
#     )
# )

# print("\n=== FLOOD DEPTH (AT-GRADE / UNKNOWN ROADS) ===")

# print(
#     at_grade_roads["max_flood_depth_m"].quantile(
#         [0, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.00]
#     )
# )

# print("\n=== USED ROADS BY DISRUPTION CLASS ===")

# summary_by_class = (
#     used_roads.groupby("disruption_class")
#     .agg(
#         road_features=("assigned_car_trips", "size"),
#         sum_of_road_assignments=("assigned_car_trips", "sum"),
#         mean_assigned_demand=("assigned_car_trips", "mean"),
#         max_assigned_demand=("assigned_car_trips", "max")
#     )
#     .sort_values(
#         "sum_of_road_assignments",
#         ascending=False
#     )
# )

# print(summary_by_class.to_string())

# print("\n=== USED ROADS BY STRUCTURE CLASS ===")

# print(
#     used_roads["road_structure_class"]
#     .value_counts()
# )

# ============================================================
# 24. Continuous flood exposure and functional importance
# ============================================================

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

# ------------------------------------------------------------
# 1. Select roads for the scatter plot
# ------------------------------------------------------------

# Include at-grade/unknown roads with positive baseline
# model-assigned OD demand.

plot_roads = vulnerability_importance[
    (vulnerability_importance["assigned_car_trips"] > 0)
    & (
        vulnerability_importance["road_structure_class"]
        == "at_grade_or_unknown"
    )
].copy()

assert len(plot_roads) == 807

# Separate roads according to the existing flood threshold.
lower_exposure = plot_roads[
    plot_roads["max_flood_depth_m"] < 0.50
]

severe_exposure = plot_roads[
    plot_roads["max_flood_depth_m"] >= 0.50
]

# Identify five highest-demand severely exposed roads.
highlight_roads = severe_exposure.nlargest(
    5, "assigned_car_trips"
).copy()


# ------------------------------------------------------------
# 2. Create the scatter plot
# ------------------------------------------------------------

fig, ax = plt.subplots(figsize=(11, 6.5))

# Roads below the severe-disruption threshold.
ax.scatter(
    lower_exposure["max_flood_depth_m"],
    lower_exposure["assigned_car_trips"],
    s=17,
    alpha=0.50,
    color="#468BAA",
    edgecolors="none",
    label="Below 0.50 m"
)

# Roads at or above the severe-disruption threshold.
ax.scatter(
    severe_exposure["max_flood_depth_m"],
    severe_exposure["assigned_car_trips"],
    s=17,
    alpha=0.50,
    color="#D95645",
    edgecolors="none",
    label="At or above 0.50 m"
)

# Highlight five high-demand, severely exposed roads.
ax.scatter(
    highlight_roads["max_flood_depth_m"],
    highlight_roads["assigned_car_trips"],
    s=85,
    facecolors="#D95645",
    edgecolors="#333333",
    linewidths=1.2,
    zorder=5,
    label="Five highest-demand severely exposed roads"
)

# Severe-disruption threshold.
ax.axvline(
    x=0.50,
    color="#B83F3F",
    linestyle="--",
    linewidth=1.4,
    alpha=0.9,
    label="Severe-disruption threshold (0.50 m)"
)


# ------------------------------------------------------------
# 3. Label the most important examples
# ------------------------------------------------------------

# Label the two highest-demand severely exposed features.
# Their demand is identical, but their flood depths differ.

label_roads = highlight_roads.head(2)

for _, road in label_roads.iterrows():

    x = road["max_flood_depth_m"]
    y = road["assigned_car_trips"]

    ax.annotate(
        f'{int(road["assigned_car_trips"]):,} trips',
        xy=(x, y),
        xytext=(0, 13),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        fontweight="bold",
        color="#333333",
        path_effects=[
            pe.withStroke(linewidth=3, foreground="white")
        ]
    )


# ------------------------------------------------------------
# 4. Add key-result annotation
# ------------------------------------------------------------

number_severely_exposed = len(severe_exposure)
number_plotted = len(plot_roads)

percentage_severely_exposed = (
    number_severely_exposed / number_plotted * 100
)

annotation_text = (
    f"{number_severely_exposed} of {number_plotted} roads "
    f"({percentage_severely_exposed:.1f}%)\n"
    "have modelled flood depths of at least 0.50 m"
)

ax.text(
    0.98,
    0.77,
    annotation_text,
    transform=ax.transAxes,
    ha="right",
    va="top",
    fontsize=11,
    bbox=dict(
        boxstyle="round,pad=0.5",
        facecolor="white",
        edgecolor="#CCCCCC",
        alpha=0.95
    )
)


# ------------------------------------------------------------
# 5. Final figure formatting
# ------------------------------------------------------------

ax.set_xlim(0, 1.80)
ax.set_ylim(0, 7300)

ax.set_xlabel(
    "Maximum modelled flood depth (m)",
    fontsize=11
)

ax.set_ylabel(
    "Baseline model-assigned car person trips",
    fontsize=11
)

ax.set_title(
    "Flood exposure versus OD-assigned demand",
    fontsize=14,
    pad=15
)

ax.grid(
    color="#DDDDDD",
    alpha=0.45,
    linewidth=0.6
)

ax.set_axisbelow(True)

ax.legend(
    loc="upper right",
    fontsize=11,
    frameon=True
)

plt.tight_layout()
plt.show()


# ------------------------------------------------------------
# 6. Validation summary
# ------------------------------------------------------------

print("\n=== FLOOD EXPOSURE–IMPORTANCE RESULTS ===")

print("Total road features plotted:", len(plot_roads))

print("Roads below 0.50 m:", len(lower_exposure))

print(
    "Roads at or above 0.50 m:",
    len(severe_exposure)
)

print(
    "Share at or above 0.50 m (%):",
    round(percentage_severely_exposed, 1)
)

print("\nFive highest-demand severely exposed roads:")

print(
    highlight_roads[
        [
            "u", "v", "key",
            "assigned_car_trips",
            "max_flood_depth_m"
        ]
    ].to_string(index=False)
)

# # ============================================================
# # 25. Export flood exposure and OD-based importance to QGIS
# # ============================================================

# # Use the existing OD output directory.
# output_dir = network_path.parent.parent / "OD_data"
# output_dir.mkdir(parents=True, exist_ok=True)

# # Export the 807 at-grade/unknown road features
# # carrying positive baseline assigned OD demand.
# importance_map = plot_roads.copy()

# # Retain all existing attributes, including:
# # - assigned_car_trips
# # - max_flood_depth_m
# # - disruption_class
# # - road_structure_class
# # - geometry

# importance_map_path = (
#     output_dir / "flood_exposure_od_importance.gpkg"
# )

# importance_map.to_file(
#     importance_map_path,
#     layer="flood_exposure_od_importance",
#     driver="GPKG"
# )

# # ============================================================
# # Validation
# # ============================================================
# assert len(importance_map) == 807

# assert (
#     importance_map["assigned_car_trips"] > 0
# ).all()

# assert (
#     importance_map["road_structure_class"]
#     == "at_grade_or_unknown"
# ).all()

# assert importance_map["max_flood_depth_m"].notna().all()

# print("\n=== FLOOD EXPOSURE–IMPORTANCE EXPORT ===")

# print("Exported road features:", len(importance_map))

# print(
#     "Maximum baseline assigned demand:",
#     importance_map["assigned_car_trips"].max()
# )

# print(
#     "Maximum flood depth (m):",
#     importance_map["max_flood_depth_m"].max()
# )

# print("Output file:", importance_map_path.resolve())
