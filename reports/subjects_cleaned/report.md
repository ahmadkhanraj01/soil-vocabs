# Cleaned subjects vs SoilVoc

Database `msp-kh-stage`, schema `validate` (read-only). Cleaning is done in CSV only; nothing is written to the DB.

## Result

- SoilVoc concepts used by records: **476 of 1464** (445 without 'broader' links)
- Records with a SoilVoc subject: **5916 of 33566 (17.6%)**, 60.1% of the 9836 records with subjects (5433 without 'broader' links)
- Before cleaning (exact labels only): 5020 records
- Including SoilVoc terms found inside longer keywords (weaker): 487 concepts, 6081 records (18.1%)

## Keywords

- Unique keywords before cleaning: 19262
- Unique keywords after cleaning: 18334
- SoilVoc: 1063 (exact 688, synonym 82, translation 98, variant 32, mapped 116, accents 2, broader 45)
- SoilVoc but ambiguous (more than one concept): 29
- SoilVoc term inside a longer keyword (weaker link): 830
- Proposed new SoilVoc terms: 92
- Category labels (SDG goals, OECD fields of science, HAL domains, INSPIRE themes, portal tags): 377
- Noise: 1046
- Not yet classified: 14897

## Cleaning steps applied (keyword parts)

- split: 2996
- language (keyword_translations.csv): 2839
- separators: 2686
- SoilVoc term inside keyword: 921
- brackets: 584
- language/synonym (manual decision): 255
- INSPIRE theme: 217
- language (SoilVoc translated labels): 127
- classification-code: 110
- numbering: 105
- portal/metadata tag: 105
- OECD field of science: 68
- HAL domain: 64
- wrapper: 48
- SDG goal: 43
- project-prefix: 18
- camelcase: 1

## Not yet classified, by record language (unique keywords)

- English: 12495
- German: 588
- Italian: 515
- French: 311
- Spanish: 252
- Dutch: 163
- Portuguese: 134
- Catalan: 61

## Top 40 not yet classified keywords (by records)

- ecosystem (179)
- carbon (171)
- soil study (116)
- effektive durchwurzelungstiefe (75)
- bodennutzbarkeit (72)
- bodengesellschaft (72)
- bodenverbreitung (67)
- durchlässigkeit (67)
- bodenform (67)
- competitiveness (63)
- new business models (63)
- bodengestaltung (62)
- bodengruppe (61)
- bodensubstrat (61)
- crop diversification (51)
- pest (47)
- dual purpose or mixed cropping (45)
- plant culture (44)
- mikrobiologie (38)
- education (33)
- outdoor horticulture and woody crops (33)
- geochemical mapping (30)
- disease control in plants (30)
- farm diversification (30)
- conservation of natural resources (29)
- habitats and biotopes (28)
- ecología (27)
- ecosystems (25)
- cartografia geologica (25)
- ecosystem research (24)
- ökosystemforschung (24)
- schema tettonico (23)
- aree sottoposte a vincolo (23)
- microbial ecology (22)
- schwermetallgehalt (22)
- plasticulture (21)
- assetto strutturale (21)
- facteur socio économique (21)
- rilievi del cfva della regione sardegna (21)
- terrestrial ecosystem (20)

## Files

- `subjects_cleaned.csv`: one row per subject part: original, cleaned, English, language, steps, status, SoilVoc concept
- `record_soilvoc.csv`: one row per record and SoilVoc concept

Language is the translation's language when one was used, otherwise the most common language of the subject's records.
