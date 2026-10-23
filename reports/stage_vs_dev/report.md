# Stage vs dev: subjects and SoilVoc

Stage = `msp-kh-stage` (schema `validate`), dev = `msp-kh-dev` (schema `validate`). Read-only.

Schema check: tables records, subjects, record_subject have identical columns in both databases.

## Records by identifier

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

## Records present in both

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

## Files

- `new_in_dev.csv`: fresh records with subjects and matched SoilVoc concepts
- `new_in_dev_with_soilvoc.csv`: fresh records that have at least one SoilVoc concept
- `new_in_dev_without_subjects.csv`: fresh records with no subjects (candidates for text extraction)
- `new_in_dev_soilvoc_concepts.csv`: SoilVoc concepts used by the fresh records
- `only_in_stage.csv`: records in stage but not in dev
- `common_subjects_changed.csv`: records in both whose subjects differ
- `full_comparison.md`, `field_changes.csv`: all other fields (title, abstract, ...) for records in both

SoilVoc matching: exact, mapped, variant, normalised and manual decisions, the same rules as `reports/subjects_vs_soilvoc`. Suggestion-only translated matches are not counted.
