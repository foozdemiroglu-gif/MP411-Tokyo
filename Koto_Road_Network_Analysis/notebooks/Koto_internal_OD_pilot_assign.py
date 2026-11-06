"""Assign Koto-only car person-trip OD pairs to directed shortest paths.

Run with --network, --od, --access-log and --output to specify input files.
The output GeoPackage keeps the source nodes/edges and adds pilot flows to edges.
"""

import argparse
import csv
import heapq
import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def access_nodes(workbook):
    """Read zone IDs and node OSM IDs from the checked access-node workbook."""
    with ZipFile(workbook) as archive:
        strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        texts = [
            "".join(t.text or "" for t in item.findall(".//x:t", NS))
            for item in strings.findall("x:si", NS)
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        mapping = {}
        for row in sheet.findall(".//x:sheetData/x:row", NS):
            cells = {cell.get("r").rstrip("0123456789"): cell for cell in row.findall("x:c", NS)}
            if "A" not in cells or "B" not in cells:
                continue

            def read(cell):
                value = cell.find("x:v", NS)
                if value is None:
                    return ""
                return texts[int(value.text)] if cell.get("t") == "s" else value.text

            zone, node_id = read(cells["A"]), read(cells["B"])
            if zone.startswith(":034") and zone in {f":{i:04d}" for i in range(340, 350)}:
                mapping[zone] = int(node_id)
    expected = {f":{i:04d}" for i in range(340, 350)}
    if set(mapping) != expected or len(set(mapping.values())) != 10:
        raise ValueError("Access log must contain ten unique checked zone nodes :0340–:0349")
    return mapping


def shortest_path(graph, origin, destination):
    distances = {origin: 0.0}
    previous = {}
    queue = [(0.0, origin)]
    while queue:
        distance, current = heapq.heappop(queue)
        if distance > distances[current] + 1e-9:
            continue
        if current == destination:
            break
        for neighbor, fid, meters in graph[current]:
            candidate = distance + meters
            if candidate + 1e-9 < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = (current, fid)
                heapq.heappush(queue, (candidate, neighbor))
    if destination not in distances:
        raise ValueError(f"No directed path from {origin} to {destination}")
    fids = []
    current = destination
    while current != origin:
        parent, fid = previous[current]
        fids.append(fid)
        current = parent
    fids.reverse()
    return distances[destination], fids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", type=Path, default=ROOT / "upload/Road_network_full.gpkg")
    parser.add_argument("--od", type=Path, default=ROOT / "upload/d-1_koto_road_modes.csv")
    parser.add_argument("--access-log", type=Path, default=ROOT / "output/Koto_OD_access_node_log.xlsx")
    parser.add_argument("--output", type=Path, default=ROOT / "output/Koto_internal_car_OD_pilot_assignment.gpkg")
    args = parser.parse_args()
    nodes = access_nodes(args.access_log)
    with args.od.open(encoding="utf-8-sig", newline="") as source:
        pairs = [
            row for row in csv.DictReader(source)
            if row["origin_area"] in nodes
            and row["destination_area"] in nodes
            and row["origin_area"] != row["destination_area"]
            and int(row["car_trips"]) > 0
        ]
    if len(pairs) != 54 or sum(int(row["car_trips"]) for row in pairs) != 28803:
        raise ValueError("Selected OD pairs differ from the audited pilot input")

    if args.output.resolve() == args.network.resolve():
        raise ValueError("Output must differ from source road network")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    shutil.copyfile(args.network, args.output)
    con = sqlite3.connect(args.output)
    try:
        # GPKG's spatial-index triggers mention these functions even for nongeometry
        # updates. Raise if a geometry-index operation is unexpectedly attempted.
        con.create_function("ST_IsEmpty", 1, lambda blob: 0)
        for name in ("ST_MinX", "ST_MaxX", "ST_MinY", "ST_MaxY"):
            def refuse(blob, operation=name):
                raise RuntimeError(f"Unexpected geometry index operation: {operation}")
            con.create_function(name, 1, refuse)

        con.execute("ALTER TABLE edges ADD COLUMN pilot_car_person_trips INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE edges ADD COLUMN pilot_od_pair_count INTEGER NOT NULL DEFAULT 0")
        con.execute("""CREATE TABLE pilot_routes (
            origin_zone TEXT, destination_zone TEXT,
            origin_node_osmid INTEGER, destination_node_osmid INTEGER,
            car_person_trips INTEGER, path_length_m REAL,
            edge_count INTEGER, edge_fids TEXT,
            PRIMARY KEY(origin_zone, destination_zone))""")
        con.execute("CREATE TABLE pilot_run_info (item TEXT PRIMARY KEY, description TEXT)")
        existing = {record[0] for record in con.execute("SELECT osmid FROM nodes")}
        if not set(nodes.values()).issubset(existing):
            raise ValueError("The selected access nodes are missing from the road graph")

        graph = defaultdict(list)
        for fid, u, v, start, end, oneway, length in con.execute(
            'SELECT fid,u,v,"from","to",oneway,length FROM edges'
        ):
            if length is None or length <= 0:
                raise ValueError(f"Invalid length on edge {fid}")
            # The saved GeoPackage condenses reverse edges on two-way streets.
            arcs = [(start, end)] if oneway else [(u, v), (v, u)]
            for tail, head in arcs:
                if tail is None or head is None:
                    raise ValueError(f"Missing directed endpoint on edge {fid}")
                graph[tail].append((head, fid, float(length)))
        for arcs in graph.values():
            arcs.sort(key=lambda arc: (arc[1], arc[0]))

        flow = defaultdict(int)
        used_by_pairs = defaultdict(int)
        for row in pairs:
            oz, dz = row["origin_area"], row["destination_area"]
            trips = int(row["car_trips"])
            meters, edge_fids = shortest_path(graph, nodes[oz], nodes[dz])
            con.execute(
                "INSERT INTO pilot_routes VALUES (?,?,?,?,?,?,?,?)",
                (oz, dz, nodes[oz], nodes[dz], trips, meters,
                 len(edge_fids), json.dumps(edge_fids, separators=(",", ":"))),
            )
            for fid in set(edge_fids):
                flow[fid] += trips
                used_by_pairs[fid] += 1
        con.executemany(
            "UPDATE edges SET pilot_car_person_trips=?,pilot_od_pair_count=? WHERE fid=?",
            [(flow[fid], used_by_pairs[fid], fid) for fid in flow],
        )
        notes = {
            "Scope": "2018 Person Trip survey car person trips between different Koto zones :0340–:0349: 54 positive pairs, 28,803 trips.",
            "Assignment": "One zone access node each; all-or-nothing directed shortest paths weighted by edges.length in meters. For one-way edges use from/to; for two-way edges allow u/v in both directions.",
            "Excluded": "15,679 car person trips within the same zone, plus all inbound/outbound trips with endpoints outside the ten Koto zones.",
            "Interpretation": "Pilot edge totals are assigned survey-based PERSON trips by car, not observed vehicle counts, calibrated volumes or congestion-aware equilibrium flows.",
            "Sensitivity": "Vary access nodes (especially zone 0346), routing weights and the study-area network extent before interpreting road criticality.",
            "Inputs": "d-1_koto_road_modes.csv; Road_network_full.gpkg; Koto_OD_access_node_log.xlsx. See Koto_internal_car_OD_pilot_inputs.xlsx for 54 prepared pairs.",
        }
        con.executemany("INSERT INTO pilot_run_info VALUES (?,?)", notes.items())
        con.commit()
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Output GeoPackage failed integrity check")
        assert con.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 6352
        assert con.execute("SELECT COUNT(*),SUM(car_person_trips) FROM pilot_routes").fetchone() == (54, 28803)
        print(json.dumps({"output": str(args.output), "od_pairs": 54,
                          "car_person_trips": 28803, "edges_with_assigned_flow": len(flow),
                          "max_edge_flow": max(flow.values())}))
    finally:
        con.close()


if __name__ == "__main__":
    main()
