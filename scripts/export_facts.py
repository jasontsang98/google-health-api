"""Export dbt fact tables as Parquet files to a local Google Drive folder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ingest_health import authenticate


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "health.duckdb"
FACT_TABLES = ("fct_exercise", "fct_badminton")


def resolve_output_dir(cli_value: str | None) -> Path:
    value = cli_value or os.getenv("GDRIVE_OUTPUT_DIR") or os.getenv("OUTPUT_DIR", "data/gold")
    if not value:
        raise RuntimeError(
            "Set GDRIVE_OUTPUT_DIR in .env or pass --output-dir with the local "
            "Google Drive-synced folder path."
        )
    return Path(value).expanduser()


def export_fact_tables(database: Path, output_dir: Path) -> list[Path]:
    if not database.exists():
        raise FileNotFoundError(
            f"DuckDB database was not found: {database}. Run dbt build first."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    with duckdb.connect(str(database), read_only=True) as connection:
        for table_name in FACT_TABLES:
            target = output_dir / f"{table_name}.parquet"
            connection.table(table_name).write_parquet(
                str(target), compression="zstd", overwrite=True
            )
            exported.append(target)
    return exported


def upload_to_drive(paths: list[Path], folder_id: str) -> None:
    service = build("drive", "v3", credentials=authenticate(), cache_discovery=False)
    for path in paths:
        escaped_name = path.name.replace("'", "\\'")
        query = (
            f"'{folder_id}' in parents and name = '{escaped_name}' "
            "and trashed = false"
        )
        matches = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id,name)",
                pageSize=10,
            )
            .execute()
            .get("files", [])
        )
        media = MediaFileUpload(str(path), mimetype="application/octet-stream", resumable=True)
        if matches:
            service.files().update(
                fileId=matches[0]["id"],
                media_body=media,
                fields="id,name",
            ).execute()
            print(f"Updated Drive file: {path.name}")
        else:
            service.files().create(
                body={"name": path.name, "parents": [folder_id]},
                media_body=media,
                fields="id,name",
            ).execute()
            print(f"Created Drive file: {path.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export fct_exercise and fct_badminton to a Drive-synced folder."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE,
        help=f"DuckDB database path (default: {DATABASE})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Local Google Drive-synced folder; overrides GDRIVE_OUTPUT_DIR.",
    )
    parser.add_argument(
        "--upload-to-drive",
        action="store_true",
        help="Upload the exported files to GOOGLE_DRIVE_FOLDER_ID.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    paths = export_fact_tables(args.database, output_dir)
    for path in paths:
        print(f"Exported {path.name} -> {path}")
    if args.upload_to_drive or os.getenv("UPLOAD_TO_DRIVE", "false").lower() == "true":
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID is required when uploading to Drive.")
        upload_to_drive(paths, folder_id)


if __name__ == "__main__":
    main()
