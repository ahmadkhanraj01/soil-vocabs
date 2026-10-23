# Stage vs dev comparison

Compares `msp-kh-stage` (DB 1) and `msp-kh-dev` (DB 2), schema `validate`, joined on `records.identifier`. Read-only. The table structure is identical in both.

Regenerate: `python scripts/compare_stage_dev.py` and `python scripts/compare_stage_dev_fields.py`.

Files: [report.md](report.md) (subjects and SoilVoc), [full_comparison.md](full_comparison.md) (every field), the CSV lists below. `field_changes.csv` (about 19 MB) is not in git; regenerate it with the second script.

# Subjects and SoilVoc

Stage = `msp-kh-stage` (schema `validate`), dev = `msp-kh-dev` (schema `validate`). Read-only.

Schema check: tables records, subjects, record_subject have identical columns in both databases.

### Records by identifier

| Group | Records | With subjects | With SoilVoc concept |
|---|---|---|---|
| Stage, all | 33,566 | 9,927 (29.6%) | 5,762 (17.2%) |
| Dev, all | 38,211 | 32,732 (85.7%) | 18,948 (49.6%) |
| In both | 12,613 | 8,332 (66.1%) | 4,633 (36.7%) |
| Only in dev (fresh) | 25,598 | 22,745 (88.9%) | 14,118 (55.2%) |
| Only in stage | 20,953 | 1,595 (7.6%) | 1,129 (5.4%) |

Records without an identifier (skipped): stage 0, dev 0. Duplicate identifiers (collapsed): stage 0, dev 0.


Stage on its own
- Stage has 33,566 records.
- 9,927 of them (29.6%) have subjects.
- 5,762 (17.2% of all stage records) have at least one SoilVoc concept.

Stage records that are also in dev
- 12,613 of the 33,566 stage records are in dev, matched by identifier. That is 37.6%.
- The other 20,953 stage records are not in dev.

### Records present in both

The 12,613 records in both are 37.6% of stage and 33.0% of dev.

| Same records | In stage | In dev | Change |
|---|---|---|---|
| Records with subjects | 8,332 (66.1%) | 9,987 (79.2%) | +1,655 |
| Subject links | 88,413 | 94,239 | +5,826 |
| Records with a SoilVoc concept | 4,633 (36.7%) | 4,830 (38.3%) | +197 |
| SoilVoc concept links | 13,389 | 14,192 | +803 |

- Subjects differ for 7,701 of 12,613 records (`common_subjects_changed.csv`).
- Gained their first subjects in dev: 1,762. Lost all subjects in dev: 107.
- Gained their first SoilVoc concept in dev: 336.

# All fields

12,613 records have the same `identifier` in stage and dev. Each field is compared after trimming whitespace; JSON is compared by content. Read-only.

Meaning: *Changed* = both have a value and they differ; *Filled in dev* = empty in stage, value in dev; *Emptied in dev* = value in stage, empty in dev.

### Field by field: records with a value, per field (stage, dev, increase / decrease)

Same 12,613 records in both databases:

| Field | Stage | Dev | Increase / decrease |
|---|---|---|---|
| title | 12,613 (100.0%) | 12,613 (100.0%) | +0 |
| abstract | 12,613 (100.0%) | 12,016 (95.3%) | -597 |
| resource_type | 12,613 (100.0%) | 12,613 (100.0%) | +0 |
| license | 5,654 (44.8%) | 5,957 (47.2%) | +303 |
| language | 12,613 (100.0%) | 12,613 (100.0%) | +0 |
| thumbnail | 650 (5.2%) | 587 (4.7%) | -63 |
| publication_date | 9,017 (71.5%) | 3,212 (25.5%) | -5,805 |
| resource_creation_date | 1,891 (15.0%) | 1,842 (14.6%) | -49 |
| resource_updated_date | 8,884 (70.4%) | 1 (0.0%) | -8,883 |
| harvest_date | 4,048 (32.1%) | 12,613 (100.0%) | +8,565 |
| spatial | 2,512 (19.9%) | 2,384 (18.9%) | -128 |
| temporal_start | 1,906 (15.1%) | 1,894 (15.0%) | -12 |
| temporal_end | 1,793 (14.2%) | 1,785 (14.2%) | -8 |
| raw_metadata | 12,613 (100.0%) | 12,613 (100.0%) | +0 |
| approval_status | 12,613 (100.0%) | 12,613 (100.0%) | +0 |
| url | 12,240 (97.0%) | 9,064 (71.9%) | -3,176 |
| subjects | 8,332 (66.1%) | 9,987 (79.2%) | +1,655 |

All records (stage 33,566, dev 38,211):

| Field | Stage | Dev | Increase / decrease |
|---|---|---|---|
| title | 33,566 (100.0%) | 38,211 (100.0%) | +4,645 |
| abstract | 33,566 (100.0%) | 36,202 (94.7%) | +2,636 |
| resource_type | 33,566 (100.0%) | 38,211 (100.0%) | +4,645 |
| license | 5,658 (16.9%) | 23,478 (61.4%) | +17,820 |
| language | 33,566 (100.0%) | 38,211 (100.0%) | +4,645 |
| thumbnail | 2,159 (6.4%) | 628 (1.6%) | -1,531 |
| publication_date | 10,711 (31.9%) | 3,482 (9.1%) | -7,229 |
| resource_creation_date | 2,781 (8.3%) | 1,967 (5.1%) | -814 |
| resource_updated_date | 10,967 (32.7%) | 1 (0.0%) | -10,966 |
| harvest_date | 16,633 (49.6%) | 38,211 (100.0%) | +21,578 |
| spatial | 4,857 (14.5%) | 2,528 (6.6%) | -2,329 |
| temporal_start | 2,853 (8.5%) | 2,283 (6.0%) | -570 |
| temporal_end | 2,482 (7.4%) | 2,098 (5.5%) | -384 |
| raw_metadata | 33,566 (100.0%) | 38,211 (100.0%) | +4,645 |
| approval_status | 33,566 (100.0%) | 38,211 (100.0%) | +4,645 |
| url | 31,575 (94.1%) | 26,271 (68.8%) | -5,304 |
| subjects | 9,927 (29.6%) | 32,732 (85.7%) | +22,805 |

