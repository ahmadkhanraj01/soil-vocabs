# Stage vs dev: full comparison of records in both

12,613 records have the same `identifier` in stage and dev. Each field is compared after trimming whitespace; JSON is compared by content. Read-only.

Meaning: *Changed* = both have a value and they differ; *Filled in dev* = empty in stage, value in dev; *Emptied in dev* = value in stage, empty in dev.

## Records with a value, per field (stage, dev, increase / decrease)

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

## All fields, including subjects (how the values differ record by record)

| Field | Same | Changed | Filled in dev | Emptied in dev | Empty in both |
|---|---|---|---|---|---|
| title | 11,251 (89.2%) | 1,362 | 0 | 0 | 0 |
| abstract | 6,943 (55.0%) | 5,073 | 0 | 597 | 0 |
| resource_type | 10,526 (83.5%) | 2,087 | 0 | 0 | 0 |
| license | 5,620 (44.6%) | 24 | 313 | 10 | 6,646 |
| language | 1 (0.0%) | 12,612 | 0 | 0 | 0 |
| thumbnail | 585 (4.6%) | 2 | 0 | 63 | 11,963 |
| publication_date | 2,978 (23.6%) | 166 | 68 | 5,873 | 3,528 |
| resource_creation_date | 1,833 (14.5%) | 8 | 1 | 50 | 10,721 |
| resource_updated_date | 0 (0.0%) | 1 | 0 | 8,883 | 3,729 |
| harvest_date | 2,064 (16.4%) | 1,984 | 8,565 | 0 | 0 |
| spatial | 2,377 (18.8%) | 1 | 6 | 134 | 10,095 |
| temporal_start | 1,876 (14.9%) | 12 | 6 | 18 | 10,701 |
| temporal_end | 1,773 (14.1%) | 7 | 5 | 13 | 10,815 |
| raw_metadata | 204 (1.6%) | 12,409 | 0 | 0 | 0 |
| approval_status | 0 (0.0%) | 12,613 | 0 | 0 | 0 |
| url | 6,960 (55.2%) | 1,865 | 239 | 3,415 | 134 |
| subjects | 2,393 (19.0%) | 5,832 | 1,762 | 107 | 2,519 |

Records with no difference in any field except `harvest_date`: 0 (0.0%).

## Subjects only

| Field | Same | Changed | Filled in dev | Emptied in dev | Empty in both |
|---|---|---|---|---|---|
| subjects (set of labels) | 2,393 (19.0%) | 5,832 | 1,762 | 107 | 2,519 |

## What the differences look like (examples from `field_changes.csv`)

- `language`: stage stores the name (`English`, `German`), dev stores the code (`en`, `de`), so almost every row differs.
- `approval_status`: stage `approved`, dev `pending` in every shared record.
- `resource_type`: stage `Other`, dev `Unknown` in many records.
- `raw_metadata`: differs in nearly all records because the harvested JSON contains a new `_version_` number; some records also have a different abstract or title in it.
- `title`: dev often drops a scale suffix (`... 1:1.000.000`) or keeps HTML and extra whitespace from the source.
- `publication_date` and `resource_updated_date`: often present in stage and empty in dev.

See `report.md` for subject and SoilVoc totals and `common_subjects_changed.csv` for the subject differences. `field_changes.csv` lists every changed, filled or emptied field with both values (cut at 300 characters; `harvest_date` is counted above but not listed).
