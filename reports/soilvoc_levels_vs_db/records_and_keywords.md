# Records, subjects and keywords vs SoilVoc

Database `msp-kh-stage`, schema `validate` (read-only). Records in total: **33566**. SoilVoc labels (pref + alt): 1849.

"Same as SoilVoc" = equal to a SoilVoc prefLabel or altLabel, ignoring case and extra spaces (after splitting on `,` and `;`). No translations, plurals or manual mappings.

| Source | Records with it | Records with a SoilVoc one | Unique values | Same as SoilVoc | SoilVoc concepts hit |
|---|---|---|---|---|---|
| Subjects (`subjects` table) | 9836 (29.3%) | 5020 (15.0%) | 19298 | 464 (2.4%) | 439 of 1464 |
| Keywords (`raw_metadata` subjects + identification.keywords) | 11079 (33.0%) | 3081 (9.2%) | 24624 | 319 (1.3%) | 296 of 1464 |
| `raw_metadata.matched_subjects` | 4595 (13.7%) | 4585 (13.7%) | 309 | 306 (99.0%) | 306 of 1464 |
| Subjects or keywords | 11282 (33.6%) | 5251 (15.6%) | | | |

Unique `subjects.label` rows (unsplit): 19279
