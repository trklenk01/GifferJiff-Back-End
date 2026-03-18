# 🎬 TenorClone Backend Setup

This project provides a PostgreSQL-backed GIF database with generated tags, ready for search and API development.

---

## 🚀 Quick Start (Windows PowerShell)

After cloning the repo, open PowerShell in the project root and run:

powershell -ExecutionPolicy Bypass -File .\setup_tenorclone.ps1

This is the **only command you need** to fully set up the database.

---

## 📦 Prerequisites

Make sure you have:

- Docker Desktop (running)
- Python 3 installed (for tag generation)
- PowerShell (Windows)

---

## ⚙️ What the Setup Script Does

Running the command above will automatically:

1. Start PostgreSQL in Docker
2. Apply database migrations
3. Seed GIF data (~300,000 GIFs)
4. Generate tags
5. Import tags into the database

---

## 🧪 Verify It Worked

Run:

docker exec -it tenorclone-db psql -U app -d tenorclone

Then:

SELECT COUNT(*) FROM gifs;
SELECT COUNT(*) FROM tags;
SELECT COUNT(*) FROM gif_tags;

---

## 🔁 Re-running Setup

powershell -ExecutionPolicy Bypass -File .\setup_tenorclone.ps1

---

## 📁 Important Files

- setup_tenorclone.ps1
- seeddata/seed_gifs_large.csv
- scripts/generate_tags_for_schema.py
- db/migrations/

---

## 🛠 Troubleshooting

Docker not running → Start Docker Desktop  
Permission error → Use ExecutionPolicy Bypass  
Missing seed → Ensure seeddata/seed_gifs_large.csv exists  

---

## ✅ Done

Your database is now ready for API development and search experiments.
