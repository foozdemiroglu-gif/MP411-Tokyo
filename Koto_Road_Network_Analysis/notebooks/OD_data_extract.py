from pathlib import Path
import pandas as pd


# ============================================================
# FILE PATHS
# ============================================================

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

D1_FILE = RAW_DIR / "d-1.csv"
ZONE_FILE = RAW_DIR / "H30_zonecode.csv"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 1. LOAD DATA
# ============================================================

zones = pd.read_csv(ZONE_FILE, dtype=str)
df = pd.read_csv(D1_FILE, dtype=str)


# ============================================================
# 2. CREATE LIST OF ALL VALID SMALL ZONES
# ============================================================

# Convert H30 small-zone codes to the same format as d-1
# Example:
# 340 -> :0340

valid_small_zones = {
    f":{int(zone):04d}"
    for zone in zones["small_zone"].dropna().unique()
}


# ============================================================
# 3. FIND KOTO SMALL ZONES
# ============================================================

koto_rows = zones[
    zones["municipality_en"].str.strip().eq("Koto Ward")
]

koto_codes = {
    f":{int(zone):04d}"
    for zone in koto_rows["small_zone"].dropna().unique()
}

print("Koto zones:")
print(sorted(koto_codes))


# ============================================================
# 4. CLEAN OD CODES
# ============================================================

df["origin_area"] = df["origin_area"].str.strip()
df["destination_area"] = df["destination_area"].str.strip()


# ============================================================
# 5. REMOVE AGGREGATE / NON-SPATIAL OD ROWS
# ============================================================

# Both origin AND destination must be genuine small zones.

valid_od_mask = (
    df["origin_area"].isin(valid_small_zones)
    & df["destination_area"].isin(valid_small_zones)
)

df = df.loc[valid_od_mask].copy()

print(f"Rows after removing aggregate zones: {len(df):,}")


# ============================================================
# 6. KEEP ONLY OD PAIRS RELATED TO KOTO
# ============================================================

origin_in_koto = df["origin_area"].isin(koto_codes)
destination_in_koto = df["destination_area"].isin(koto_codes)

koto_mask = origin_in_koto | destination_in_koto

koto_od = df.loc[koto_mask].copy()


# ============================================================
# 7. CLASSIFY KOTO RELATION
# ============================================================

koto_od["origin_in_koto"] = (
    koto_od["origin_area"].isin(koto_codes)
)

koto_od["destination_in_koto"] = (
    koto_od["destination_area"].isin(koto_codes)
)


def classify_trip(row):

    if row["origin_in_koto"] and row["destination_in_koto"]:
        return "internal"

    elif row["origin_in_koto"]:
        return "outbound"

    else:
        return "inbound"


koto_od["koto_relation"] = koto_od.apply(
    classify_trip,
    axis=1
)


# ============================================================
# 8. SAVE DETAILED PURPOSE DATASET
# ============================================================

koto_od.to_csv(
    PROCESSED_DIR / "d-1_koto_all_clean.csv",
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# 9. CREATE OD TOTAL MATRIX
# ============================================================

# Keep only the existing Total-purpose rows.
# DO NOT sum all purposes + Total together.

koto_totals = koto_od[
    koto_od["trip_purpose"].eq("Total")
].copy()


# ============================================================
# 10. CHECK FOR TRUE DUPLICATE OD PAIRS
# ============================================================

duplicates = koto_totals.duplicated(
    subset=[
        "origin_area",
        "destination_area"
    ],
    keep=False
)

if duplicates.any():

    print("\nWARNING: duplicate OD pairs found:")

    print(
        koto_totals.loc[
            duplicates,
            [
                "origin_area",
                "destination_area",
                "total_trips"
            ]
        ]
        .sort_values(
            ["origin_area", "destination_area"]
        )
        .to_string(index=False)
    )

else:
    print("\nNo duplicate OD pairs found.")


# ============================================================
# 11. SAVE CLEAN OD MATRIX
# ============================================================

koto_totals.to_csv(
    PROCESSED_DIR / "koto_od_clean.csv",
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# 12. SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("CLEAN KOTO OD DATA")
print("=" * 60)

print(f"Detailed Koto rows: {len(koto_od):,}")
print(f"Unique OD total rows: {len(koto_totals):,}")

print("\nKoto relation:")
print(
    koto_totals["koto_relation"]
    .value_counts()
    .to_string()
)