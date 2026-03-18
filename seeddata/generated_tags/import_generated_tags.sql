BEGIN;

-- 1) Insert canonical tags
\copy tags(name) FROM '/tmp/generated_tags/generated_tags.csv' WITH (FORMAT csv, HEADER true);

-- 2) Insert gif <-> tag pairs by joining tag names back to tag IDs
CREATE TEMP TABLE generated_gif_tags_stage (
  gif_id uuid,
  tag_name text,
  confidence real,
  source text
) ON COMMIT DROP;

\copy generated_gif_tags_stage(gif_id, tag_name, confidence, source) FROM '/tmp/generated_tags/generated_gif_tags.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO gif_tags(gif_id, tag_id, confidence, source)
SELECT s.gif_id, t.id, s.confidence, s.source
FROM generated_gif_tags_stage s
JOIN tags t ON t.name = s.tag_name
ON CONFLICT (gif_id, tag_id) DO NOTHING;

-- 3) Optional aliases
CREATE TEMP TABLE generated_tag_aliases_stage (
  alias text,
  tag_name text
) ON COMMIT DROP;

\copy generated_tag_aliases_stage(alias, tag_name) FROM '/tmp/generated_tags/generated_tag_aliases.csv' WITH (FORMAT csv, HEADER true);

INSERT INTO tag_aliases(alias, tag_id)
SELECT s.alias, t.id
FROM generated_tag_aliases_stage s
JOIN tags t ON t.name = s.tag_name
ON CONFLICT (alias) DO NOTHING;

COMMIT;