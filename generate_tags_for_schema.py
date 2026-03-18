#!/usr/bin/env python3
"""
Generate and optionally import GIF tags for the Tenor-clone schema.

Tailored to the schema in 001_init.sql:
- gifs(id uuid primary key, ...)
- tags(id bigserial primary key, name text unique, ...)
- gif_tags(gif_id uuid, tag_id bigint, confidence real, source text, ...)
- tag_aliases(alias text primary key, tag_id bigint)

Input CSV is expected to match the loaded GIF seed format, including:
  id, source_url, cdn_url, title, rating, width, height,
  filesize_bytes, duration_ms, is_deleted, is_unlisted, created_at

Default behavior:
1. Read GIF titles from the CSV
2. Generate candidate tags from title text
3. Keep tags that occur at least --min-count times globally
4. Write COPY-friendly CSVs and an import.sql file

Optional:
- --postgres-url can insert directly if psycopg is installed
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Sequence

WORD_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)?")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "for", "from", "gif", "gifs", "he", "her", "hers", "him", "his", "i", "if",
    "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "out",
    "she", "so", "that", "the", "their", "them", "there", "they", "this", "to",
    "up", "was", "we", "what", "when", "where", "who", "why", "with", "you", "your",
    "na", "via", "official", "channel", "tv", "movie", "film", "video"
}

# Words that are often useful search tags even if short or slangy.
KEEP_WORDS = {
    "lol", "lmao", "wtf", "omg", "nba", "nfl", "mlb", "nhl", "ufc", "wow", "no",
    "yes", "cat", "dog", "sad", "mad", "funny", "cute", "dance", "happy", "angry",
    "fail", "win", "mood", "shocked", "flirting", "crying", "laughing", "kiss", "party"
}

# Very common boilerplate / low-signal tokens seen in title imports.
DROP_WORDS = {
    "reaction", "sticker", "memes", "meme", "animated", "clip", "media", "giphy"
}

ALIASES = {
    "lmao": "lol",
    "lmfao": "lol",
    "rofl": "lol",
    "wtheck": "wtf",
    "omfg": "omg",
    "kitty": "cat",
    "puppy": "dog",
}


@dataclass(frozen=True)
class GifRow:
    gif_id: str
    title: str


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_tag(tag: str) -> str:
    tag = tag.lower().strip()
    tag = tag.replace("&", " and ")
    tag = NON_ALNUM_RE.sub(" ", tag)
    tag = normalize_space(tag)
    return tag


def tokenize(title: str) -> List[str]:
    title = title.lower()
    words = [m.group(0).strip("'-") for m in WORD_RE.finditer(title)]
    cleaned: List[str] = []
    for w in words:
        if not w:
            continue
        if w in DROP_WORDS:
            continue
        if len(w) == 1 and w not in {"g", "r"}:
            continue
        if w in STOPWORDS and w not in KEEP_WORDS:
            continue
        if w.isdigit() and len(w) < 4:
            continue
        cleaned.append(w)
    return cleaned


def generate_candidates(title: str, max_unigrams: int, max_bigrams: int) -> List[str]:
    tokens = tokenize(title)
    seen: set[str] = set()
    results: List[str] = []

    def add(tag: str) -> None:
        tag = normalize_tag(tag)
        if not tag or tag in seen:
            return
        if len(tag) < 2 and tag not in KEEP_WORDS:
            return
        if tag in STOPWORDS and tag not in KEEP_WORDS:
            return
        seen.add(tag)
        results.append(tag)

    # Unigrams first.
    unigram_count = 0
    for tok in tokens:
        if tok in ALIASES:
            add(ALIASES[tok])
        add(tok)
        unigram_count += 1
        if unigram_count >= max_unigrams:
            break

    # Adjacent bigrams can help searches like "fist bump" or "ice cube".
    bigram_count = 0
    for a, b in zip(tokens, tokens[1:]):
        if a in STOPWORDS or b in STOPWORDS:
            continue
        if a in DROP_WORDS or b in DROP_WORDS:
            continue
        if a.isdigit() or b.isdigit():
            continue
        phrase = f"{a} {b}"
        add(phrase)
        bigram_count += 1
        if bigram_count >= max_bigrams:
            break

    return results


def iter_rows(csv_path: str) -> Iterator[GifRow]:
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = {"id", "title"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        for row in reader:
            gif_id = (row.get("id") or "").strip()
            title = normalize_space(row.get("title") or "")
            if not gif_id or not title:
                continue
            yield GifRow(gif_id=gif_id, title=title)


def count_tags(csv_path: str, max_unigrams: int, max_bigrams: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in iter_rows(csv_path):
        counts.update(generate_candidates(row.title, max_unigrams, max_bigrams))
    return counts


def ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_outputs(
    csv_path: str,
    outdir: str,
    min_count: int,
    max_count: int,
    source_label: str,
    confidence: float,
    max_unigrams: int,
    max_bigrams: int,
    include_aliases: bool,
) -> dict[str, str]:
    ensure_outdir(outdir)

    counts = count_tags(csv_path, max_unigrams, max_bigrams)
    allowed = {
        tag for tag, count in counts.items()
        if count >= min_count and (max_count <= 0 or count <= max_count)
    }

    tags_path = os.path.join(outdir, "generated_tags.csv")
    gif_tags_path = os.path.join(outdir, "generated_gif_tags.csv")
    aliases_path = os.path.join(outdir, "generated_tag_aliases.csv")
    stats_path = os.path.join(outdir, "generated_tag_stats.txt")
    sql_path = os.path.join(outdir, "import_generated_tags.sql")

    with open(tags_path, "w", encoding="utf-8", newline="") as f_tags, \
         open(gif_tags_path, "w", encoding="utf-8", newline="") as f_gif_tags:
        tags_writer = csv.writer(f_tags)
        gif_tags_writer = csv.writer(f_gif_tags)

        tags_writer.writerow(["name"])
        gif_tags_writer.writerow(["gif_id", "tag_name", "confidence", "source"])

        for tag in sorted(allowed):
            tags_writer.writerow([tag])

        written_pairs = 0
        for row in iter_rows(csv_path):
            tags = [t for t in generate_candidates(row.title, max_unigrams, max_bigrams) if t in allowed]
            for tag in tags:
                gif_tags_writer.writerow([row.gif_id, tag, confidence, source_label])
                written_pairs += 1

    if include_aliases:
        canonical_present = {canonical for canonical in ALIASES.values() if canonical in allowed}
        with open(aliases_path, "w", encoding="utf-8", newline="") as f_aliases:
            aliases_writer = csv.writer(f_aliases)
            aliases_writer.writerow(["alias", "tag_name"])
            for alias, canonical in sorted(ALIASES.items()):
                if canonical in canonical_present:
                    aliases_writer.writerow([alias, canonical])
    else:
        with open(aliases_path, "w", encoding="utf-8", newline="") as f_aliases:
            aliases_writer = csv.writer(f_aliases)
            aliases_writer.writerow(["alias", "tag_name"])

    with open(stats_path, "w", encoding="utf-8") as f_stats:
        f_stats.write(f"input_csv={csv_path}\n")
        f_stats.write(f"retained_unique_tags={len(allowed)}\n")
        f_stats.write(f"min_count={min_count}\n")
        f_stats.write(f"max_count={max_count}\n")
        f_stats.write("\nTop 200 tags by frequency:\n")
        for tag, count in counts.most_common(200):
            marker = "*" if tag in allowed else " "
            f_stats.write(f"{marker} {count:>6}  {tag}\n")

    sql = f"""-- Import generated tags into the current schema.
-- Run this after the gifs table has already been populated.

BEGIN;

-- 1) Insert canonical tags
\\copy tags(name) FROM '{tags_path.replace('\\', '/')}' WITH (FORMAT csv, HEADER true)

-- If duplicate names exist, do a safe upsert instead of raw COPY:
-- INSERT INTO tags(name)
-- SELECT name FROM generated staging table
-- ON CONFLICT (name) DO NOTHING;

-- 2) Insert gif <-> tag pairs by joining tag names back to tag IDs
CREATE TEMP TABLE generated_gif_tags_stage (
  gif_id uuid,
  tag_name text,
  confidence real,
  source text
) ON COMMIT DROP;

\\copy generated_gif_tags_stage(gif_id, tag_name, confidence, source)
FROM '{gif_tags_path.replace('\\', '/')}' WITH (FORMAT csv, HEADER true);

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

\\copy generated_tag_aliases_stage(alias, tag_name)
FROM '{aliases_path.replace('\\', '/')}' WITH (FORMAT csv, HEADER true);

INSERT INTO tag_aliases(alias, tag_id)
SELECT s.alias, t.id
FROM generated_tag_aliases_stage s
JOIN tags t ON t.name = s.tag_name
ON CONFLICT (alias) DO NOTHING;

COMMIT;
"""
    with open(sql_path, "w", encoding="utf-8") as f_sql:
        f_sql.write(sql)

    return {
        "tags_csv": tags_path,
        "gif_tags_csv": gif_tags_path,
        "aliases_csv": aliases_path,
        "stats_txt": stats_path,
        "import_sql": sql_path,
        "unique_tags": str(len(allowed)),
    }


def insert_postgres(postgres_url: str, generated_dir: str) -> None:
    try:
        import psycopg  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Direct Postgres import requires psycopg. Install with: pip install psycopg[binary]"
        ) from exc

    tags_csv = os.path.join(generated_dir, "generated_tags.csv")
    gif_tags_csv = os.path.join(generated_dir, "generated_gif_tags.csv")
    aliases_csv = os.path.join(generated_dir, "generated_tag_aliases.csv")

    with psycopg.connect(postgres_url) as conn:
        with conn.cursor() as cur:
            with open(tags_csv, "r", encoding="utf-8") as f:
                next(f)
                for line in f:
                    tag = line.rstrip("\n")
                    cur.execute(
                        "INSERT INTO tags(name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                        (tag,),
                    )

            with open(gif_tags_csv, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cur.execute(
                        """
                        INSERT INTO gif_tags(gif_id, tag_id, confidence, source)
                        SELECT %s::uuid, t.id, %s::real, %s
                        FROM tags t
                        WHERE t.name = %s
                        ON CONFLICT (gif_id, tag_id) DO NOTHING
                        """,
                        (
                            row["gif_id"],
                            row["confidence"],
                            row["source"],
                            row["tag_name"],
                        ),
                    )

            with open(aliases_csv, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row["alias"] or not row["tag_name"]:
                        continue
                    cur.execute(
                        """
                        INSERT INTO tag_aliases(alias, tag_id)
                        SELECT %s, t.id
                        FROM tags t
                        WHERE t.name = %s
                        ON CONFLICT (alias) DO NOTHING
                        """,
                        (row["alias"], row["tag_name"]),
                    )
        conn.commit()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate tags for the Tenor-clone GIF schema")
    parser.add_argument("--input", required=True, help="Path to seed_gifs_large.csv")
    parser.add_argument("--outdir", required=True, help="Directory for generated CSV and SQL output")
    parser.add_argument("--min-count", type=int, default=3, help="Keep tags seen at least this many times globally")
    parser.add_argument("--max-count", type=int, default=0, help="Drop tags seen more than this many times (0 disables)")
    parser.add_argument("--source", default="auto", help="gif_tags.source value")
    parser.add_argument("--confidence", type=float, default=0.65, help="gif_tags.confidence value")
    parser.add_argument("--max-unigrams", type=int, default=8, help="Max single-word tags per GIF")
    parser.add_argument("--max-bigrams", type=int, default=4, help="Max bigram tags per GIF")
    parser.add_argument("--include-aliases", action="store_true", help="Write a small alias file for common slang/synonyms")
    parser.add_argument("--postgres-url", help="Optional psycopg connection URL for direct import")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    outputs = write_outputs(
        csv_path=args.input,
        outdir=args.outdir,
        min_count=args.min_count,
        max_count=args.max_count,
        source_label=args.source,
        confidence=args.confidence,
        max_unigrams=args.max_unigrams,
        max_bigrams=args.max_bigrams,
        include_aliases=args.include_aliases,
    )

    print("Generated:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")

    if args.postgres_url:
        insert_postgres(args.postgres_url, args.outdir)
        print("\nDirect Postgres import complete.")
    else:
        print("\nNo direct DB import requested. Use the generated CSVs or import_generated_tags.sql.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
