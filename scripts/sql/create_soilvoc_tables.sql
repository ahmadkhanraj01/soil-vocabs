-- Option 1 DDL: SoilVoc vocabulary + subject links (see reports/soilvoc_levels_vs_db/IMPLEMENTATION.md)
-- Idempotent: safe to run more than once. Run as k2xadmin.

BEGIN;

CREATE TABLE IF NOT EXISTS validate.soilvoc_types (
    code        text PRIMARY KEY,          -- SoilVoc URI, e.g. https://w3id.org/eusoilvoc#Soil
    level       smallint CHECK (level BETWEEN 1 AND 8),  -- NULL = detached procedure concept (no hierarchy level)
    parent_code text REFERENCES validate.soilvoc_types(code),
    name        text NOT NULL,             -- preferred label
    alt_labels  text[]                    -- all alternative labels in one array
);
-- allow NULL level for the ~249 detached procedure concepts (level stays range-checked)
ALTER TABLE validate.soilvoc_types ALTER COLUMN level DROP NOT NULL;

CREATE TABLE IF NOT EXISTS validate.subject_soilvoc (
    subject_id    uuid NOT NULL REFERENCES validate.subjects(id) ON DELETE CASCADE,
    soilvoc_code  text NOT NULL REFERENCES validate.soilvoc_types(code),
    link_type     text NOT NULL CHECK (link_type IN
        ('exact', 'synonym', 'translation', 'mapped', 'variant', 'broader', 'inside')),
    part          text,                    -- fragment of the label that matched (after a split)
    reviewed      boolean NOT NULL DEFAULT false,
    PRIMARY KEY (subject_id, soilvoc_code)
);

CREATE INDEX IF NOT EXISTS subject_soilvoc_code_idx
    ON validate.subject_soilvoc (soilvoc_code);

COMMIT;
