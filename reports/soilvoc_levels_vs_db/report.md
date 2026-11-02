# SoilVoc levels vs database keywords

Database: msp-kh-stage, schema validate (DB1) (read-only). Matches from `compare_subjects_to_soilvoc.py` (tiers exact, mapped, variant, normalised*, manual; translated suggestions not counted).

SoilVoc concepts found in the database: **460 of 1464 (31.4%)**.

`db_records` sums record counts over all keywords matched to a concept, so a record with two matching keywords counts twice: read it as an upper bound. A keyword matched to several concepts (e.g. FAO and WRB `Andosols`) counts for each of them.

## Coverage by level

| Level | Concepts | In DB | % | DB keywords | DB records |
|---|---|---|---|---|---|
| 1 | 17 | 15 | 88.2% | 56 | 6594 |
| 2 | 144 | 89 | 61.8% | 165 | 3976 |
| 3 | 300 | 135 | 45.0% | 220 | 4475 |
| 4 | 305 | 109 | 35.7% | 164 | 4269 |
| 5 | 242 | 57 | 23.6% | 66 | 391 |
| 6 | 133 | 29 | 21.8% | 51 | 523 |
| 7 | 5 | 0 | 0.0% | 0 | 0 |
| 8 | 69 | 26 | 37.7% | 27 | 50 |
| detached | 249 | 0 | 0.0% | 0 | 0 |

## Coverage by top concept

| Top concept | Concepts | In DB | % | DB records |
|---|---|---|---|---|
| soil properties | 509 | 162 | 31.8% | 4537 |
| soil substance | 147 | 64 | 43.5% | 2338 |
| soil processes | 144 | 50 | 34.7% | 949 |
| soil management | 96 | 33 | 34.4% | 622 |
| soil indicators | 64 | 18 | 28.1% | 858 |
| soil threats | 63 | 31 | 49.2% | 1857 |
| soil description | 42 | 12 | 28.6% | 817 |
| soil functions | 39 | 27 | 69.2% | 753 |
| planetary phenomena | 30 | 20 | 66.7% | 681 |
| land cover | 15 | 11 | 73.3% | 768 |
| soil phenomena | 15 | 5 | 33.3% | 13 |
| soil sciences | 15 | 10 | 66.7% | 995 |
| geology | 13 | 6 | 46.2% | 920 |
| physiography | 10 | 3 | 30.0% | 52 |
| soil | 7 | 5 | 71.4% | 3790 |
| ecosystem services | 5 | 2 | 40.0% | 90 |
| soil health | 1 | 1 | 100.0% | 238 |

## Most used concepts

| Level | Concept | Top concept | DB records | Keywords |
|---|---|---|---|---|
| 1 | soil | soil | 3558 | soil (2120); boden (723); suolo (207); ejpsoil (198); bodem (94); ejp soil (77); sol (3... |
| 1 | geology | geology | 780 | geology (566); geologie (131); geologia (82); geology [science] (1) |
| 4 | land use | soil indicators | 562 | land use (252); bodennutzung (150); utilizzo del territorio (42); land-use (28); soil u... |
| 4 | soil types | soil properties | 500 | soil types (259); soil type (135); bodentyp (85); bodentypen (15); soil-type (6) |
| 3 | soil maps | soil description | 492 | thematic-map (254); bodenkarte (152); soil map (54); bodemkaart (30); soil maps (2) |
| 3 | soil temperature | soil properties | 480 | soil temperature (249); temperature (231) |
| 1 | soil properties | soil properties | 453 | soil properties (244); basic soil properties (133); bodeneigenschaften (71); soil prope... |
| 1 | land cover | land cover | 443 | land cover (276); copertura del suolo (102); bodenbedeckung (43); landcover (18); land-... |
| 1 | soil sciences | soil sciences | 419 | bodenkunde (134); soil science (122); soil sciences (109); soils and soil sciences (27)... |
| 2 | soil biology | soil sciences | 362 | soil microbiology (146); microbiology (120); bodenbiologie (64); bodembiologie (16); so... |
| 2 | soil pollution | soil threats | 362 | soil pollution (122); bodenbelastung (106); bodendekontamination (62); soil contaminati... |
| 2 | soil erosion | soil threats | 348 | soil erosion (178); bodenerosion (74); erosion (47); erosión (24); bodemerosie (22); so... |
| 4 | soil organic carbon | soil properties | 339 | soil organic carbon (209); soil carbon (59); organic carbon (37); soc (33); soil organi... |
| 2 | soil degradation | soil threats | 324 | soil degradation (146); bodendegradation (70); soil degradation processes (46); land de... |
| 2 | climate | planetary phenomena | 301 | climate change (205); climate (96) |
| 1 | soil functions | soil functions | 292 | soil functions (165); bodenfunktion (80); bodenfunktionen (20); bodemfunctie (15); soil... |
| 4 | soil cohesion | soil properties | 242 | soil cohesion (242) |
| 1 | soil health | soil health | 238 | soil health (236); soil condition (1); soil conditions (1) |
| 4 | iron | soil substance | 238 | iron (237); fe2+ (1) |
| 3 | soil water | soil substance | 212 | water (114); soil water (58); water resources (24); water management (16) |
| 3 | soil texture | soil properties | 196 | bodenart (113); bodemtextuur (30); texture (27); soil texture (23); soil-texture (3) |
| 3 | soil air | soil substance | 193 | soil air (116); bodenluft (62); bodemlucht (15) |
| 2 | soil productivity | soil properties | 190 | soil productivity (150); soil fertility (39); soil nutrient content (1) |
| 6 | agricultural soils | soil properties | 186 | landwirtschaftliche fläche (67); agricultural (35); agricultural land (20); farmland (2... |
| 3 | soil moisture | soil substance | 184 | soil moisture (96); bodenfeuchtigkeit (69); bodemvocht (15); soil-moisture (4) |

## Branches with no database hits (level 2, 3+ concepts)

- geology › rock outcrops (3 concepts)
- soil management › soil management equipment (3 concepts)
- soil properties › soil consistence (9 concepts)

## Files

- `soilvoc_levels_with_db.csv`: the levels CSV plus DB keywords, record counts and subtree roll-ups
- `coverage_by_level.csv`, `coverage_by_branch.csv`: the tables above as CSV
