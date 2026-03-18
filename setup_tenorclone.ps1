param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ContainerName = "tenorclone-db",
    [string]$DbUser = "app",
    [string]$DbName = "tenorclone",
    [string]$GifCsv = ".\seeddata\seed_gifs_large.csv",
    [string]$TagScript = ".\generate_tags_for_schema.py",
    [string]$GeneratedTagDir = ".\seeddata\generated_tags_min10",
    [int]$MinCount = 10,
    [switch]$IncludeAliases,
    [switch]$SkipTagGeneration,
    [switch]$SkipGifImport,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"

function Step($message) {
    Write-Host "`n=== $message ===" -ForegroundColor Cyan
}

function Require-Path($path, $label) {
    if (-not (Test-Path $path)) {
        throw "$label not found: $path"
    }
}

function Run-Process {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $false)][string[]]$ArgumentList = @()
    )

    $display = $FilePath
    if ($ArgumentList.Count -gt 0) {
        $display += " " + ($ArgumentList -join " ")
    }
    Write-Host $display -ForegroundColor DarkGray

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Exec-Psql($sql) {
    Run-Process "docker" @(
        "exec", "-i", $ContainerName,
        "psql", "-U", $DbUser, "-d", $DbName,
        "-v", "ON_ERROR_STOP=1",
        "-c", $sql
    )
}

function Copy-And-RunSqlFile($localFile, $remoteFile) {
    Require-Path $localFile "SQL file"
    Run-Process "docker" @("cp", $localFile, "${ContainerName}:$remoteFile")
    Run-Process "docker" @(
        "exec", "-i", $ContainerName,
        "psql", "-U", $DbUser, "-d", $DbName,
        "-v", "ON_ERROR_STOP=1",
        "-f", $remoteFile
    )
}

function Wait-ForDb() {
    Step "Waiting for Postgres to be ready"
    for ($i = 0; $i -lt 60; $i++) {
        & docker exec $ContainerName pg_isready -U $DbUser -d $DbName *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Postgres is ready." -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for Postgres in container '$ContainerName'."
}

function Apply-Migrations() {
    Step "Applying migrations"
    $migrationFiles = @(
        ".\db\migrations\000_migrations.sql",
        ".\db\migrations\001_init.sql",
        ".\db\migrations\003_view_gif_with_tags.sql",
        ".\db\migrations\004_search_function.sql",
        ".\db\migrations\005_trgm_aliases.sql"
    )

    foreach ($file in $migrationFiles) {
        Copy-And-RunSqlFile $file ("/tmp/" + [System.IO.Path]::GetFileName($file))
    }
}

function Import-Gifs() {
    Step "Importing GIF seed data"
    Require-Path $GifCsv "GIF CSV"

    Exec-Psql "TRUNCATE gif_tags, tag_aliases, tags, gifs RESTART IDENTITY CASCADE;"
    Run-Process "docker" @("cp", $GifCsv, "${ContainerName}:/tmp/seed_gifs_large.csv")
    Exec-Psql "\copy gifs(id,source_url,cdn_url,title,rating,width,height,filesize_bytes,duration_ms,is_deleted,is_unlisted,created_at) FROM '/tmp/seed_gifs_large.csv' WITH (FORMAT csv, HEADER true)"
}

function Generate-Tags() {
    Step "Generating tags"
    Require-Path $TagScript "Tag generation script"
    Require-Path $GifCsv "GIF CSV"

    $pythonArgs = @(
        $TagScript,
        "--input", $GifCsv,
        "--outdir", $GeneratedTagDir,
        "--min-count", $MinCount.ToString()
    )

    if ($IncludeAliases) {
        $pythonArgs += "--include-aliases"
    }

    Run-Process "python" $pythonArgs

    $sqlFile = Join-Path $GeneratedTagDir "import_generated_tags.sql"
    Require-Path $sqlFile "Generated import SQL"

    $content = Get-Content $sqlFile -Raw
    $normalizedDir = ($GeneratedTagDir -replace '\\', '/').TrimStart('.')
    $normalizedDir = $normalizedDir.TrimStart('/')
    $content = $content -replace [regex]::Escape("./$normalizedDir/"), "/tmp/generated_tags/"

    $content = $content -replace "\\copy\s+generated_gif_tags_stage\(gif_id,\s*tag_name,\s*confidence,\s*source\)\s*`r?`nFROM\s+'[^']+'\s+WITH\s*\(FORMAT csv, HEADER true\);", "\\copy generated_gif_tags_stage(gif_id, tag_name, confidence, source) FROM '/tmp/generated_tags/generated_gif_tags.csv' WITH (FORMAT csv, HEADER true);"
    $content = $content -replace "INSERT INTO gif_tags\(gif_id,\s*tag_id,\s*confidence,\s*source\)\s*`r?`nSELECT s\.gif_id, t\.id, s\.confidence, s\.source\s*`r?`nFROM generated_gif_tags_stage s\s*`r?`nJOIN tags t ON t\.name = s\.tag_name\s*`r?`nON CONFLICT \(gif_id,\s*tag_id\) DO NOTHING;", "INSERT INTO gif_tags(gif_id, tag_id, confidence, source)`r`nSELECT s.gif_id, t.id, s.confidence, s.source`r`nFROM generated_gif_tags_stage s`r`nJOIN tags t ON t.name = s.tag_name`r`nJOIN gifs g ON g.id = s.gif_id`r`nON CONFLICT (gif_id, tag_id) DO NOTHING;"
    $content = $content -replace "\\copy\s+generated_tag_aliases_stage\(alias,\s*tag_name\)\s*`r?`nFROM\s+'[^']+'\s+WITH\s*\(FORMAT csv, HEADER true\);", "\\copy generated_tag_aliases_stage(alias, tag_name) FROM '/tmp/generated_tags/generated_tag_aliases.csv' WITH (FORMAT csv, HEADER true);"

    Set-Content -Path $sqlFile -Value $content -NoNewline
}

function Import-Tags() {
    Step "Importing generated tags"
    Require-Path $GeneratedTagDir "Generated tag directory"
    $sqlFile = Join-Path $GeneratedTagDir "import_generated_tags.sql"
    Require-Path $sqlFile "Generated import SQL"

    Exec-Psql "TRUNCATE gif_tags, tag_aliases, tags RESTART IDENTITY CASCADE;"
    Run-Process "docker" @("cp", $GeneratedTagDir, "${ContainerName}:/tmp/generated_tags")
    Run-Process "docker" @("cp", $sqlFile, "${ContainerName}:/tmp/import_generated_tags.sql")
    Run-Process "docker" @(
        "exec", "-i", $ContainerName,
        "psql", "-U", $DbUser, "-d", $DbName,
        "-v", "ON_ERROR_STOP=1",
        "-f", "/tmp/import_generated_tags.sql"
    )
}

function Show-Counts() {
    Step "Final counts"
    Exec-Psql "SELECT COUNT(*) AS gifs FROM gifs;"
    Exec-Psql "SELECT COUNT(*) AS tags FROM tags;"
    Exec-Psql "SELECT COUNT(*) AS gif_tags FROM gif_tags;"
    Exec-Psql "SELECT COUNT(*) AS tag_aliases FROM tag_aliases;"
}

Step "Starting database container"
if (Test-Path $ComposeFile) {
    Run-Process "docker" @("compose", "-f", $ComposeFile, "up", "-d", "db")
} else {
    Run-Process "docker" @("compose", "up", "-d", "db")
}

Wait-ForDb

if (-not $SkipMigrations) {
    Apply-Migrations
}

if (-not $SkipGifImport) {
    Import-Gifs
}

if (-not $SkipTagGeneration) {
    Generate-Tags
}

Import-Tags
Show-Counts

Step "Setup complete"
Write-Host "Try this to sanity-check results:" -ForegroundColor Green
Write-Host 'docker exec -it tenorclone-db psql -U app -d tenorclone -c "SELECT * FROM gif_with_tags LIMIT 5;"' -ForegroundColor Yellow
