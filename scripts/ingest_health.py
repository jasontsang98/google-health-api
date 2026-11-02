"""Ingest Google Health exercise data into versioned raw and current Parquet layers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pyarrow as pa
import pyarrow.parquet as pq
import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession, Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEALTH_URL = "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints"
HEALTH_SCOPE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SCOPES = [HEALTH_SCOPE, DRIVE_SCOPE]
TOKEN_PATH = ROOT / "token.json"


def required_env(name: str, *aliases: str) -> str:
    for candidate in (name, *aliases):
        value = os.getenv(candidate)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {', '.join((name, *aliases))}")


def authenticate() -> Credentials:
    """Load, refresh, or create local OAuth credentials for the Health API."""

    credentials: Credentials | None = None
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    stored_scopes: set[str] = set()
    if refresh_token:
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            client_id=required_env("GOOGLE_CLIENT_ID"),
            client_secret=required_env("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES,
        )
        credentials.refresh(Request())
        return credentials
    elif TOKEN_PATH.exists():
        token_data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        raw_scopes = token_data.get("scopes", token_data.get("scope", []))
        if isinstance(raw_scopes, str):
            raw_scopes = raw_scopes.split()
        stored_scopes = set(raw_scopes)
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    granted_scopes = (
        stored_scopes
        if stored_scopes
        else set(credentials.scopes or []) if credentials else set()
    )
    if credentials and credentials.valid and set(SCOPES).issubset(granted_scopes):
        return credentials
    if credentials and credentials.expired and credentials.refresh_token and set(SCOPES).issubset(granted_scopes):
        credentials.refresh(Request())
    else:
        client_config = {
            "installed": {
                "client_id": required_env("GOOGLE_CLIENT_ID"),
                "client_secret": required_env("GOOGLE_CLIENT_SECRET"),
                "auth_uri": os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri": os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/")
        port = urlparse(redirect_uri).port or 8080
        credentials = flow.run_local_server(
            port=port,
            open_browser=True,
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )

    if credentials is None:
        raise RuntimeError("Unable to create Google Health API credentials")
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def fetch_health_data(credentials: Credentials, url: str) -> dict[str, Any]:
    session = AuthorizedSession(credentials)
    records: list[Any] = []
    page_token: str | None = None
    while True:
        params: dict[str, str] = {"pageSize": "1000"}
        if page_token:
            params["pageToken"] = page_token
        response = session.get(url, params=params, timeout=60)
        if not response.ok:
            detail = response.text.strip()
            raise RuntimeError(
                f"Health API request failed with HTTP {response.status_code}: {detail}"
            )
        payload = response.json()
        records.extend(payload.get("dataPoints", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            return {"dataPoints": records}


def scalar_or_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def flatten_data_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in payload.get("dataPoints", []):
        exercise = point.get("exercise", {})
        interval = exercise.get("interval", {})
        source = point.get("dataSource", {})
        row: dict[str, Any] = {
            "name": point.get("name"),
            "data_source_recording_method": source.get("recordingMethod"),
            "data_source_platform": source.get("platform"),
            "interval_start_time": interval.get("startTime"),
            "interval_start_utc_offset": interval.get("startUtcOffset"),
            "interval_end_time": interval.get("endTime"),
            "interval_end_utc_offset": interval.get("endUtcOffset"),
        }
        for key, value in exercise.items():
            if key != "interval":
                row[f"exercise_{key}"] = scalar_or_json(value)
        rows.append(row)
    return rows


def write_run(payload: dict[str, Any], data_root: Path, run_at: datetime) -> dict[str, Path]:
    run_id = run_at.strftime("%Y%m%dT%H%M%SZ")
    ingest_date = run_at.strftime("%Y-%m-%d")
    raw_dir = data_root / "raw" / "google_health" / "exercise" / f"ingest_date={ingest_date}" / f"run_id={run_id}"
    current_dir = data_root / "bronze" / "current"
    raw_dir.mkdir(parents=True, exist_ok=True)
    current_dir.mkdir(parents=True, exist_ok=True)

    raw_json = raw_dir / "data.json"
    raw_parquet = raw_dir / "data.parquet"
    current_parquet = current_dir / "exercise.parquet"
    raw_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    table = pa.Table.from_pylist(flatten_data_points(payload))
    pq.write_table(table, raw_parquet, compression="zstd")
    current_temp = current_parquet.with_suffix(".tmp.parquet")
    pq.write_table(table, current_temp, compression="zstd")
    os.replace(current_temp, current_parquet)

    metadata = raw_dir / "run_metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "ingested_at": run_at.isoformat(),
                "record_count": len(payload.get("dataPoints", [])),
                "raw_json": str(raw_json),
                "raw_parquet": str(raw_parquet),
                "current_parquet": str(current_parquet),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"raw_json": raw_json, "raw_parquet": raw_parquet, "current_parquet": current_parquet}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override DATA_ROOT from .env")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    configured_data_root = args.data_root or Path(os.getenv("DATA_ROOT", "data"))
    data_root = (
        configured_data_root
        if configured_data_root.is_absolute()
        else ROOT / configured_data_root
    )
    credentials = authenticate()
    payload = fetch_health_data(credentials, os.getenv("HEALTH_API_URL", DEFAULT_HEALTH_URL))
    paths = write_run(payload, data_root, datetime.now(UTC))
    print(f"Ingested {len(payload.get('dataPoints', []))} exercise records")
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        raise
