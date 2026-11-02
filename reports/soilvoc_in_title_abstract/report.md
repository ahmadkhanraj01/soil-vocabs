# SoilVoc terms in record titles and abstracts

Database `msp-kh-stage`, schema `validate` (read-only). Matching: whole words, case-insensitive, simple singular/plural, English SoilVoc labels only. Labels under 3 characters skipped: .

## Records

- Records in total: 33566 (33566 with a title or abstract)
- Records with at least one SoilVoc term in title or abstract: **24264 (72.3%)**
- Records without subjects: 23730; of these, 17365 (73.2%) contain a SoilVoc term
- Deepest SoilVoc level found per record (deeper = more specific term): level 1: 1877, level 2: 2345, level 3: 3847, level 4: 10278, level 5: 2351, level 6: 2839, level 7: 7, level 8: 720

## SoilVoc concepts

- Concepts found in at least one record: **699 of 1464 (47.7%)**
- Level 1: 16 of 17 found (94.1%)
- Level 2: 106 of 144 found (73.6%)
- Level 3: 184 of 300 found (61.3%)
- Level 4: 164 of 305 found (53.8%)
- Level 5: 82 of 242 found (33.9%)
- Level 6: 75 of 133 found (56.4%)
- Level 7: 4 of 5 found (80.0%)
- Level 8: 65 of 69 found (94.2%)
- Level detached: 3 of 249 found (1.2%)

## Very common terms (in 10% or more of records)

These are too general to say much on their own; a record is better described by its deepest terms.

- soil (level 1): 16607 records
- crop (level 3): 6058 records
- climate (level 2): 4232 records
- nitrogen (level 4): 4147 records
- biomass (level 4): 3782 records

## Most found concepts (top 30)

- soil (level 1, soil): 16607 records (title 9940, abstract 16112, without subjects 11808)
- crop (level 3, land cover): 6058 records (title 1742, abstract 5886, without subjects 4942)
- climate (level 2, planetary phenomena): 4232 records (title 706, abstract 4135, without subjects 3000)
- nitrogen (level 4, soil substance): 4147 records (title 1606, abstract 3870, without subjects 3514)
- biomass (level 4, soil properties): 3782 records (title 730, abstract 3723, without subjects 3161)
- inputs (level 4, soil indicators): 2628 records (title 220, abstract 2586, without subjects 2039)
- emissions (level 4, soil indicators): 2332 records (title 818, abstract 2304, without subjects 1837)
- roots (level 4, land cover): 2323 records (title 531, abstract 2283, without subjects 1748)
- trees (level 4, land cover): 2248 records (title 479, abstract 2193, without subjects 1947)
- soil organic carbon (level 4, soil properties): 2197 records (title 791, abstract 2063, without subjects 1800)
- vegetation (level 3, land cover): 2078 records (title 278, abstract 2043, without subjects 1536)
- season (level 2, planetary phenomena): 2006 records (title 122, abstract 1977, without subjects 1702)
- land use (level 4, soil indicators): 1715 records (title 451, abstract 1663, without subjects 1153)
- soil properties (level 1, soil properties): 1542 records (title 342, abstract 1436, without subjects 1139)
- lead (level 4, soil threats): 1391 records (title 38, abstract 1372, without subjects 1099)
- grasses (level 4, land cover): 1314 records (title 218, abstract 1295, without subjects 1175)
- soil organic matter (level 4, soil substance): 1223 records (title 278, abstract 1168, without subjects 1007)
- phosphorus (level 4, soil substance): 1190 records (title 340, abstract 1130, without subjects 968)
- clay (level 4, soil properties): 1162 records (title 80, abstract 1157, without subjects 797)
- weather (level 2, planetary phenomena): 1150 records (title 44, abstract 1141, without subjects 613)
- soil health (level 1, soil health): 1105 records (title 299, abstract 1066, without subjects 771)
- soil water (level 3, soil substance): 1039 records (title 192, abstract 1008, without subjects 791)
- precipitation (level 3, planetary phenomena): 1021 records (title 136, abstract 1014, without subjects 766)
- irrigation (level 2, soil management): 960 records (title 292, abstract 930, without subjects 758)
- soil moisture (level 3, soil substance): 921 records (title 130, abstract 908, without subjects 669)
- building (level 2, land cover): 912 records (title 119, abstract 858, without subjects 742)
- ecosystem services (level 1, ecosystem services): 837 records (title 159, abstract 822, without subjects 543)
- crop yield (level 3, soil functions): 795 records (title 162, abstract 765, without subjects 635)
- soil quality (level 2, soil properties): 783 records (title 225, abstract 752, without subjects 603)
- topsoil (level 2, soil): 733 records (title 162, abstract 699, without subjects 418)

## Files

- `concept_hits.csv`: per SoilVoc concept, how many records mention it in title, abstract, either, and among records without subjects
- `record_hits.csv`: per record, the SoilVoc concepts found in title and abstract and the deepest (most specific) ones

## Limits

- Only English labels: German, Italian, Dutch etc. abstracts are under-counted.
- A word match is not meaning: "soil" in "we did not sample soil" still counts; very general terms (soil, water, climate) match almost everything.
- FAO, WRB and USDA versions of the same soil type (e.g. Luvisols) are separate concepts, so one mention counts for each.
- These are suggestions for records, not checked subjects.
