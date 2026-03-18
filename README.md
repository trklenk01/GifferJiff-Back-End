# GifferJiff Backend Database Setup

This project uses **PostgreSQL running in Docker**. The database schema
is created using versioned SQL migrations and populated with seed GIF
metadata.

Follow the steps below to start the database and seed it on a new
machine.

------------------------------------------------------------------------

# Prerequisites

Install the following before starting:

-   **Git**
-   **Docker Desktop** (includes Docker Compose)
-   **WSL2** (Windows only)

Ensure **Docker Desktop is running** before executing the commands
below.

------------------------------------------------------------------------

# 1. Clone the Repository

``` bash
git clone <repository-url>
cd GifferJiff-Back-End
```

------------------------------------------------------------------------

# 2. Start the PostgreSQL Database

Start the database container:

``` bash
docker compose up -d db
```

Verify the container is running:

``` bash
docker ps
```

You should see a container similar to:

    tenorclone-db

------------------------------------------------------------------------

# 3. Run Database Migrations

Apply the database schema:

``` bash
docker compose run --rm db_migrate
```

This command:

-   waits for PostgreSQL to start
-   runs all SQL files in `/db/migrations`
-   records applied migrations in `schema_migrations`

------------------------------------------------------------------------

# 4. Seed the Database

Populate the database with GIF metadata from the seed dataset.

Run this command **from the root of the repository**:

``` bash
docker exec -i tenorclone-db psql -U app -d tenorclone -c "\copy gifs(id,source_url,cdn_url,title,rating,width,height,filesize_bytes,duration_ms,is_deleted,is_unlisted,created_at) FROM STDIN WITH (FORMAT csv, HEADER true)" < seeddata/seed_gifs_large.csv
```

This streams the CSV file from your local machine into the PostgreSQL
container and inserts the records into the `gifs` table.

------------------------------------------------------------------------

# 5. Verify the Database

Check that the data was inserted successfully:

``` bash
docker exec -it tenorclone-db psql -U app -d tenorclone -c 'SELECT COUNT(*) FROM gifs;'
```

You should see something similar to:

     count
    -------
     300000

You can also open the PostgreSQL shell:

``` bash
docker exec -it tenorclone-db psql -U app -d tenorclone
```

List tables:

``` sql
\dt
```

Exit the shell:

``` sql
\q
```

------------------------------------------------------------------------

# Daily Development Workflow

Start the database:

``` bash
docker compose up -d db
```

If new migrations were added after pulling changes:

``` bash
docker compose run --rm db_migrate
```

------------------------------------------------------------------------

# Reset the Database (Clean Rebuild)

If something breaks or you want to rebuild the database from scratch:

``` bash
docker compose down -v
docker compose up -d db
docker compose run --rm db_migrate
```

Then run the seed command again.

⚠️ This deletes **all local database data**.

------------------------------------------------------------------------

# Useful Commands

### Start database

``` bash
docker compose up -d db
```

### Stop database

``` bash
docker compose down
```

### Re-run migrations

``` bash
docker compose run --rm db_migrate
```

### Open PostgreSQL CLI

``` bash
docker exec -it tenorclone-db psql -U app -d tenorclone
```

### List tables

``` sql
\dt
```

### View sample GIF records

``` sql
SELECT * FROM gifs LIMIT 10;
```

------------------------------------------------------------------------

# Troubleshooting

## Container name already in use

If Docker reports the container already exists:

``` bash
docker compose down
docker rm -f tenorclone-db
docker compose up -d db
```

------------------------------------------------------------------------

## No tables appear after migration

If `\dt` shows **no relations**:

``` bash
docker compose down -v
docker compose up -d db
docker compose run --rm db_migrate
```

Then run the seed command again.

------------------------------------------------------------------------

## Migration script errors (`\r`, invalid option, etc.)

This usually happens due to **Windows CRLF line endings**.

Convert scripts to **LF**.

In VS Code:

1.  Open the script file
2.  Click `CRLF` in the bottom-right
3.  Change to `LF`
4.  Save

------------------------------------------------------------------------

# Local Database Configuration

Default values (defined in `docker-compose.yml`):

  Setting    Value
  ---------- ------------
  Host       localhost
  Port       5432
  Database   tenorclone
  User       app
