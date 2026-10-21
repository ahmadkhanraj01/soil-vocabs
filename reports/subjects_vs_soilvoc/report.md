# Subject keywords vs SoilVoc

Database `msp-kh-stage`, schema `validate` (read-only). SoilVoc concepts: 1464.

## Summary

| Question | Number |
|---|---|
| Unique subjects in the database (`subjects` rows) | 20169 (20120 ignoring case and spaces) |
| Unique keywords after splitting `,` `;` | 19941 (18819 without noise) |
| SoilVoc concepts | 1464 (1023 general concepts, 192 properties, 249 procedures) |
| SoilVoc unique searchable labels (pref + alt) | 1849 |
| Exact matches | 462 |
| Partial matches | 91 (70 mapped through AGROVOC/GEMET/USDA, 21 plural or UK/US spelling variants) |
| Matches after cleaning rules A1-A7 (`normalised*` tiers) | 48 |
| Matches from manual decisions (`manual` tier) | 130 |
| All matches | 731 (3.9% of non-noise keywords; 553 / 2.9% before cleaning rules and manual decisions) |
| Suggested only: translated labels (`translated_curated` 81, `translated_mt` 25; not counted above) | 106 keywords, 4 more records |
| No match | 17982 |
| Records in total | 33566 |
| Records with subjects | 9927 (29.6%) |
| Records with a SoilVoc subject | 5762 (17.2% of all records, 58.0% of records with subjects; 5082 / 15.1% before cleaning rules and manual decisions) |
| SoilVoc concepts hit by at least one keyword | 456 of 1464 (31.1%) |

Partial means a mapped or variant match, not word-inside-word matching.
Noise is codes, numbers, dates, URLs, SDG/OECD labels and keywords under 3 characters.

## Matches by tier

| Tier | Unique keywords | % of non-noise | Records reached |
|---|---|---|---|
| exact | 462 | 2.5% | 5019 |
| mapped | 70 | 0.4% | 622 |
| variant | 21 | 0.1% | 87 |
| normalised | 35 | 0.2% | 133 |
| normalised_path | 11 | 0.1% | 13 |
| normalised_prefix | 2 | 0.0% | 247 |
| manual | 130 | 0.7% | 3196 |
| translated_curated | 81 | 0.4% | 225 |
| translated_mt | 25 | 0.1% | 59 |
| none | 17982 | 95.6% | 6779 |
| noise | 1122 | 5.6% | 8847 |

## Curation

- Decisions on file: 698 (synonym 83, broader 47, new_term 101, noise 448, skip 19); 0 imported from the review sheet in this run
- `curation/review_sheet.csv`: 500 undecided keywords to review (top 500 by records)
- `curation/soilvoc_new_terms.csv`: 79 proposed new terms
- `curation/soilvoc_synonym_candidates.csv`: 130 proposed synonyms / broader links

## Top matched keywords

| Keyword | Tier | Records | SoilVoc concept |
|---|---|---|---|
| soil | exact | 2120 | soil |
| boden | manual | 723 | soil |
| geology | exact | 566 | geology |
| land cover | exact | 276 | land cover |
| soil types | exact | 259 | soil types |
| thematic-map | manual | 254 | soil maps |
| land use | exact | 252 | land use |
| soil temperature | exact | 249 | soil temperature |
| soil properties | exact | 244 | soil properties |
| soil cohesion | exact | 242 | soil cohesion |
| iron | exact | 237 | iron |
| soil health | exact | 236 | soil health |
| temperature | manual | 231 | soil temperature |
| soil organic carbon | exact | 209 | soil organic carbon |
| suolo | manual | 207 | soil |
| climate change | manual | 204 | climate |
| ejpsoil | normalised_prefix | 198 | soil |
| soil erosion | exact | 178 | soil erosion |
| carbonate | exact | 173 | carbonate |
| soil microfauna | exact | 173 | soil microfauna |

## Top unmatched keywords

| Keyword | Records |
|---|---|
| agriculture | 555 |
| biodiversity | 260 |
| ecosystem | 178 |
| carbon | 161 |
| soil literacy | 145 |
| bodenschutz | 144 |
| forestry | 90 |
| remote sensing | 90 |
| food security | 88 |
| climate change (incl. ghg reduction, adaptation and mitigation, and other air related issues) | 77 |
| environmental monitoring | 74 |
| bodengesellschaft | 72 |
| bodennutzbarkeit | 72 |
| biodiversity and nature | 71 |
| bodenfruchtbarkeit | 68 |
| bodenform | 67 |
| bodenverbreitung | 67 |
| organic farming | 67 |
| agro-ecology | 62 |
| bodengestaltung | 62 |
| bodengruppe | 61 |
| bodensubstrat | 61 |
| aquaculture | 57 |
| arable crops | 56 |
| pfas | 56 |
| effektive-durchwurzelungstiefe | 55 |
| bodengüte | 54 |
| carbon cycle | 54 |
| durchlässigkeit | 53 |
| carbon dioxide | 52 |

## Files

- `matched.csv`: keyword, tier, records, SoilVoc concept
- `unmatched.csv`: keywords with no SoilVoc match, by record count
- `noise.csv`: codes, numbers, dates, URLs and SDG/OECD labels left out of the percentages
- `soilvoc_not_in_db.csv`: SoilVoc concepts that no keyword matched
