# Google Health Exercise Dashboard

This project extracts Google Health exercise data, stores a versioned local data archive, transforms it with dbt and DuckDB, and displays the results in Streamlit.

The current workflow is local-only. Google Drive upload is reserved for a later phase.

## Project workflow

```text
Google Health API
        |
        v
scripts/ingest_health.py
        |
        +--> data/raw/                         immutable JSON and Parquet runs
        +--> data/bronze/current/exercise.parquet
                         |
                         v
                    dbt build
                         |
                         v
                    health.duckdb
                         |
                         v
               scripts/export_facts.py
                         |
                         v
                  Google Drive folder
                         |
                         v
                    Streamlit dashboard
```

The dbt layers are:

- `stg_exercise`: reads the current bronze Parquet file.
- `int_exercise`: filters Fitbit data, normalizes names and timestamps, and converts duration to numeric seconds.
- `int_exercise_metrics`: turns the heterogeneous metrics JSON into rows.
- `fct_exercise`: analytical exercise-session table.
- `fct_badminton`: badminton-specific pivoted metrics table.

## Requirements

- Windows PowerShell
- Python 3.13 or 3.14 (the current virtual environment is tested on Python 3.14.9; `.python-version` currently specifies 3.13)
- A Google Cloud project with the Google Health API enabled
- A Google OAuth client ID and client secret
- OAuth redirect URI registered as `http://localhost:8080/`

## Initial setup

From the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy the environment template and fill in the OAuth values:

```powershell
Copy-Item .env.example .env
```

Required or commonly used `.env` settings:

```dotenv
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GOOGLE_TOKEN_URI=https://oauth2.googleapis.com/token
GOOGLE_REDIRECT_URI=http://localhost:8080/
HEALTH_API_URL=https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints
DATA_ROOT=data
```

Keep `.env` and `token.json` private. They are excluded by `.gitignore`.

## Ingest Google Health data

Run the ingestion script:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\ingest_health.py
```

On the first run, Google OAuth opens a browser for consent. After authorization, the refresh token is stored locally in `token.json`. Later runs reuse the saved credentials and refresh the access token when required.

The script fetches all API pages and writes:

```text
data/raw/google_health/exercise/ingest_date=YYYY-MM-DD/run_id=YYYYMMDDTHHMMSSZ/
    data.json
    data.parquet
    run_metadata.json

data/bronze/current/exercise.parquet
```

To store the data layers on another drive, set an absolute path in `.env`:

```dotenv
DATA_ROOT=G:\GoogleHealth\data
```

Or override it for one run:

```powershell
python scripts\ingest_health.py --data-root G:\GoogleHealth\data
```

## Build the dbt models

Create the local DuckDB profile if it does not exist:

```powershell
Copy-Item profiles.yml.example profiles.yml
```

Check the dbt connection:

```powershell
dbt debug --profiles-dir .
```

Build or refresh all models and tests:

```powershell
dbt build --profiles-dir .
```

The command creates or refreshes `health.duckdb`. The database file is local and ignored by Git.

## Export fact tables to Google Drive

For a Google Drive folder that is synced to this computer, set its local path in `.env`:

```dotenv
GDRIVE_OUTPUT_DIR=G:\GoogleHealth\facts
```

Then export the dbt fact tables after each successful build:

```powershell
python scripts\export_facts.py
```

This writes or refreshes these files in the configured folder:

```text
fct_exercise.parquet
fct_badminton.parquet
```

You can also provide the destination for a single run without changing `.env`:

```powershell
python scripts\export_facts.py --output-dir G:\GoogleHealth\facts
```

This uses the local Drive sync folder; it does not call the Google Drive API. The Drive desktop client handles synchronization after the files are written.

To upload through the Google Drive API instead, set the destination folder ID and enable uploads:

```dotenv
UPLOAD_TO_DRIVE=true
GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id
```

Then run the same command. The script updates existing files with the stable names or creates them if they do not exist:

```powershell
python scripts\export_facts.py --upload-to-drive
```

For GitHub Actions, store `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, and `GOOGLE_DRIVE_FOLDER_ID` as encrypted repository secrets. The workflow can then run ingestion, `dbt build`, and this export command without accessing a local `G:` drive.

`--profiles-dir .` tells dbt to use the repository root as the directory containing `profiles.yml`. In PowerShell, an alias can make this shorter:

```powershell
Set-Alias dbt-local dbt
```

The alias lasts for the current terminal session. The project can also use a PowerShell profile if a permanent alias is preferred.

## Query the transformed data

Show sample rows:

```powershell
dbt show --profiles-dir . --inline "select * from fct_exercise limit 10"
dbt show --profiles-dir . --inline "select * from fct_badminton limit 10"
```

Inspect the columns in a table:

```powershell
dbt show --profiles-dir . --inline "select * from pragma_table_info('stg_exercise')"
```

The dbt models are materialized into DuckDB tables. The SQL files under `models/` are transformation definitions, while the resulting tables are stored in `health.duckdb`.

## Run the dashboard

Build the database first, then start Streamlit:

```powershell
streamlit run app.py
```

Open the local URL shown by Streamlit, normally `http://localhost:8501`.

The dashboard currently provides:

- A one-year GitHub-style exercise calendar.
- Overview metrics with walking excluded as noise.
- Average active minutes, calories, and heart rate by exercise type.
- A badminton-only detail tab based on `fct_badminton`.
- Session selection by start time with KPI cards.
- Heart-rate zone minutes and percentage-of-session trend charts.

## Useful commands

```powershell
# Check the ingestion command options
python scripts\ingest_health.py --help

# Run dbt model and data tests
dbt test --profiles-dir .

# Remove generated dbt build artifacts
dbt clean --profiles-dir .
```

## Troubleshooting

### OAuth redirect URI mismatch

The redirect URI must match exactly in both places:

1. Google Cloud Console OAuth client settings.
2. `.env` as `GOOGLE_REDIRECT_URI`.

For the current local flow, use:

```text
http://localhost:8080/
```

### Re-authorize Google OAuth

Delete the local token and run ingestion again:

```powershell
Remove-Item token.json
python scripts\ingest_health.py
```

### Dashboard says `health.duckdb` was not found

Run `dbt build --profiles-dir .` before starting Streamlit.

### dbt cannot find the profile

Confirm that `profiles.yml` exists in the repository root and run commands with `--profiles-dir .`.

## Repository safety

The following are intentionally not tracked:

- `.env`
- `token.json`
- `data/`
- `health.duckdb`
- `.venv/`
- dbt `target/` and package directories

