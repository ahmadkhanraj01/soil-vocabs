# Subjects vs SoilVoc: before and after

Stage database `msp-kh-stage`, schema `validate`. Read-only: nothing was written to the database.
Final run of `scripts/compare_subjects_to_soilvoc.py`. Full detail is in `report.md`.

## Before and after

| | Before (rules only) | After (cleaning rules + 698 manual decisions) |
|---|---|---|
| Unique subjects (`subjects` rows) | 20,169 | 20,169 |
| Unique keywords after splitting `,` `;` | 19,941 | 19,941 |
| Keywords that count (not noise) | 19,267 | 18,819 |
| Exact matches | 462 | 462 |
| Mapped (AGROVOC/GEMET/USDA) + variants | 91 | 91 |
| Cleaning rules A1-A7 | 0 | 48 |
| Manual decisions | 0 | 130 |
| **All matches** | **553 (2.9%)** | **731 (3.9%)** |
| Records with subjects | 9,927 (29.6%) | 9,927 (29.6%) |
| **Records with a SoilVoc subject** | **5,082 (15.1% of all records, 51.2% of records with subjects)** | **5,762 (17.2% of all records, 58.0% of records with subjects)** |
| SoilVoc concepts hit | 450 of 1,464 | 456 of 1,464 |

"Before" is the first run: exact, mapped and variant matches only. "After" is the final run.
The non-noise count fell because 448 keywords were judged to be noise (portal tags, place names, discipline codes).

## Why this is the end of matching

- Every keyword with 14 or more records has been reviewed. The rest is a long tail of about 18,000 keywords with a few records each, so a single decision adds almost nothing.
- Most of the gain left depends on SoilVoc itself: 79 proposed new terms in `curation/soilvoc_new_terms.csv` (agriculture, biodiversity, soil fertility, soil protection, remote sensing and others).
- 19 keywords were left as `skip` because the meaning is unclear (for example German `bodenform`).

## Translated labels (suggestions only)

`curation/translated_labels.json` is the multilingual SoilVoc label list from `soilwise-he/metadata-augmentation` (`keyword-extractor/concepts_multilingual.json`, MIT licence; en/fr/de/it/es/nl/pt, partly machine-translated with DeepL). The script matches keywords against the non-English labels by exact comparison, with no model. These matches are **not counted** in the numbers above: 106 keywords would match, but they would reach only 4 more records, and some are wrong (Italian `emergenza` = emergency, not seedling emergence). They are listed in `curation/translated_review.csv`. A keyword with a decision in `keyword_decisions.csv` is never suggested.

## Records without subjects

Matching can only help the 9,927 records that have subjects. For the other records, see `../../LLM_EXTRACTION.md` (LLM suggestions from title and abstract, with a progress dashboard; experimental).

## Files

| File | Content |
|---|---|
| `report.md` | all numbers, tiers, top matched and unmatched keywords |
| `matched.csv` | keywords that match SoilVoc: tier, records, concept label and URI, rule |
| `unmatched.csv` | keywords with no match, with record counts |
| `noise.csv` | codes, tags and other non-subjects |
| `soilvoc_not_in_db.csv` | SoilVoc concepts that no keyword reaches (1,008) |
| `../../curation/keyword_decisions.csv` | the 698 manual decisions |
| `../../curation/soilvoc_new_terms.csv` | proposed new SoilVoc terms, grouped |
| `../../curation/soilvoc_synonym_candidates.csv` | proposed altLabels for existing concepts |

## Caveat

Many manual decisions were prepared by Claude and not yet checked by a person. Spot-check `keyword_decisions.csv` (especially `synonym` and `broader`) before the decisions are used for anything else.
