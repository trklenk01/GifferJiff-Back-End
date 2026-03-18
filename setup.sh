#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting TenorClone setup..."

# --- CONFIG ---
DB_CONTAINER="tenorclone-db"
DB_NAME="tenorclone"
DB_USER="app"

SEED_FILE="seeddata/seed_gifs_large.csv"
GEN_DIR="seeddata/generated_tags_min10"

# --- 1. Start DB ---
echo "📦 Starting PostgreSQL container..."
docker compose up -d db

echo "⏳ Waiting for DB to be ready..."
until docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" > /dev/null 2>&1; do
  sleep 1
done

echo "✅ DB is ready"

# --- 2. Run migrations ---
echo "📜 Applying migrations..."
for f in db/migrations/*.sql; do
  echo "Running $f"
  docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$f"
done

# --- 3. Seed GIFs ---
echo "🎞️ Seeding GIF data..."

docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "\
\copy gifs(id,source_url,cdn_url,title,rating,width,height,filesize_bytes,duration_ms,is_deleted,is_unlisted,created_at) \
FROM STDIN WITH (FORMAT csv, HEADER true)" < "$SEED_FILE"

echo "✅ GIFs seeded"

# --- 4. Generate tags ---
echo "🏷️ Generating tags..."

python3 scripts/generate_tags_for_schema.py \
  --input "$SEED_FILE" \
  --outdir "$GEN_DIR" \
  --min-count 10 \
  --include-aliases

echo "✅ Tags generated"

# --- 5. Copy generated files into container ---
echo "📂 Copying generated files into container..."

docker exec "$DB_CONTAINER" mkdir -p /tmp/generated_tags

docker cp "$GEN_DIR/generated_tags.csv" "$DB_CONTAINER:/tmp/generated_tags/"
docker cp "$GEN_DIR/generated_gif_tags.csv" "$DB_CONTAINER:/tmp/generated_tags/"
docker cp "$GEN_DIR/generated_tag_aliases.csv" "$DB_CONTAINER:/tmp/generated_tags/"
docker cp "$GEN_DIR/import_generated_tags.sql" "$DB_CONTAINER:/tmp/"

# --- 6. Import tags ---
echo "📥 Importing tags into database..."

docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f /tmp/import_generated_tags.sql

echo "🎉 Setup complete!"