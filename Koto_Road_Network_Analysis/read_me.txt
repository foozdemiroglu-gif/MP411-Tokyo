KOTO ROAD NETWORK ANALYSIS
==========================

Project: The Urban Bathtub of Tokyo – Multidisciplinary Project (MDP Group 411)
Study area: Koto City, Tokyo, Japan

PURPOSE
-------
This folder contains the files used for the road-network component of the
Koto City flood-resilience research project. The analysis examines potential
road disruption under the Heavy Rain inundation scenario, structural network
connectivity and fragmentation, accessibility between selected origin–destination
(OD) zones, and the relationship between flood exposure and OD-based road
importance.

EXISTING FOLDER STRUCTURE
-------------------------
Koto_Road_Network_Analysis/
|
|-- qgis/                    QGIS project files and associated project material
|-- outputs/                 Generated analysis outputs
|   `-- tables/              Output tables
|-- notebooks/               Python notebooks used for analysis and processing
|-- data/
|   |-- raw/                 Original input data and currently stored supporting CSVs
|   |   |-- H30_gis/         Survey planning-zone GIS data
|   |   |-- d-1              Japanese Person Trip OD source data
|   |   |-- H30_zonecode     Planning-zone code reference data
|   |   |-- od_access_nodes  Selected OD network access nodes
|   |   |-- OD_koto_only     Koto City OD data subset
|   |   |-- shinsui_koutounaibu  Inner-river inundation input data
|   |   |-- shinsui_sumidagawa  Sumida River inundation input data
|   |   `-- weak_links      Supporting critical-infrastructure data
|   `-- processed/           GIS-ready and other processed analysis data
|       |-- boundary/        Study-area boundary data
|       |-- koutounaibu/     Processed inner-river inundation data
|       |-- OD_data/         Processed OD data
|       |-- road_network/    Road-network data
|       |-- sumidagawa/      Processed Sumida River inundation data
|       |-- weak_links/      Processed supporting infrastructure data
|       |-- HeavyRain_impact.gpkg
|       |-- HeavyRain_koto_raster.tif
|       `-- HeavyRain_koto_raster.tif.aux.xml  Raster auxiliary metadata
|-- cache/                   Cached and temporary processing files
`-- .vscode/                 Local Visual Studio Code settings

NOTE ON FILENAMES
-----------------
The listings for files in data/raw/ above reproduce the base names visible in
Windows Explorer. Some extensions were hidden in that view; consult the actual
files for their precise extensions. The names and existing locations have been
preserved intentionally to avoid breaking project references.

HOW THE CONTENTS RELATE TO THE ANALYSIS
---------------------------------------
1. Input data are stored in data/raw/, including the Person Trip OD records,
   planning-zone reference information, flood-depth inputs and supporting data.
2. Prepared spatial layers and derived data are stored in data/processed/.
3. Python analysis notebooks are stored in notebooks/.
4. QGIS project files are stored in qgis/.
5. Generated results are stored in outputs/, with numerical tables in
   outputs/tables/.

Not every item currently in data/raw/ is an untouched source file:
od_access_nodes and OD_koto_only are selection/processing products. The folder
layout is retained as used in the existing analysis rather than reorganised.

KEY DATA SOURCES
----------------
- OpenStreetMap: road-network source, processed using OSMnx.
- Official Koto City / Tokyo flood-inundation data: Heavy Rain and supporting
  inundation datasets; consult the research report for scenario details.
- e-Stat: Tokyo metropolitan Person Trip survey OD data (d-1):
  https://www.e-stat.go.jp/stat-search/files?page=1&layout=datalist&toukei=00600550&tstat=000001151670&cycle=0&tclass1=000001151671&stat_infid=000032066127&tclass2val=0
- Tokyo Person Trip Survey: H30 planning-zone GIS boundaries and zone-code data:
  https://www.tokyo-pt.jp/data/01_01

The OD-based analysis uses the ten Koto City planning zones 0340–0349,
represented by selected road-network access nodes. It evaluates 54 directed OD
pairs with positive selected car person-trip demand; these do not describe all
travel in Koto City.

PORTABILITY AND REPRODUCTION
----------------------------
WARNING: The original QGIS projects use absolute file paths. Until those
references are converted and tested, the projects may not load all layers on
another computer. Python notebooks may also contain machine-specific paths.

Keep the current directory names and internal file locations unchanged when
copying the project. Before treating this folder as fully reproducible:
- Update and verify QGIS data-source paths.
- Inspect notebooks for absolute paths and other local dependencies.
- Document Python package versions and notebook execution order.
- Test opening the QGIS projects and running the analysis from a different
  local directory.

These steps are not represented here as already completed.

SHARING AND DATA MANAGEMENT
---------------------------
This folder is an organisational record of the research workspace, not a
statement that every included item can be published. Verify redistribution
permissions for original datasets before uploading them to a public GitHub
repository. Review outputs for confidential or identifiable material. Do not
publish interview transcripts, consent forms, recordings or personal data.
Exclude unnecessary cache files and machine-specific settings from a public
code repository where appropriate.

For detailed methods, assumptions, results and limitations, consult the final
research report, especially the road-network methodology, results and Appendix D.
