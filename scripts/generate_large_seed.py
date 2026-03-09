import csv
import uuid
import random
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path("seeddata/giphy-dataset/giphy.csv")
OUTPUT = Path("seeddata/seed_gifs_large.csv")

TARGET_ROWS = 300000

RATINGS = ["g", "pg", "pg13"]
EXTRA_WORDS = [
    "funny", "reaction", "meme", "lol",
    "happy", "sad", "excited", "wow",
    "shocked", "clapping", "facepalm"
]

def to_int(value):
    try:
        if value is None:
            return None
        value = str(value).strip()
        if value == "":
            return None
        return int(value)
    except Exception:
        return None

def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"Could not find {INPUT.resolve()}")

    rows = []

    with INPUT.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        print("Detected columns:")
        print(fieldnames)

        for r in reader:
            url = (r.get("Web Archive Link") or "").strip()
            title = (r.get("GIPHY Title") or "gif").strip()
            filesize = to_int(r.get("File Size (In Bytes)"))

            if not url:
                continue

            rows.append((url, title, filesize))

    print(f"Loaded {len(rows)} base gifs")

    if not rows:
        raise RuntimeError("No usable rows found in giphy.csv")

    now = datetime.now(timezone.utc).isoformat()

    with OUTPUT.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow([
            "id",
            "source_url",
            "cdn_url",
            "title",
            "rating",
            "width",
            "height",
            "filesize_bytes",
            "duration_ms",
            "is_deleted",
            "is_unlisted",
            "created_at"
        ])

        for i in range(TARGET_ROWS):
            url, title, filesize = random.choice(rows)

            extra = random.choice(EXTRA_WORDS)
            new_title = f"{title} {extra}".strip()

            writer.writerow([
                str(uuid.uuid4()),
                url,
                url,
                new_title,
                random.choice(RATINGS),
                "",   # width unknown
                "",   # height unknown
                filesize if filesize is not None else "",
                "",   # duration unknown
                "false",
                "false",
                now
            ])

            if i > 0 and i % 50000 == 0:
                print(f"Generated {i} rows")

    print(f"Done. Output written to {OUTPUT}")

if __name__ == "__main__":
    main()