"""Download SOP .docx files from Azure Blob Storage using sop.csv as the manifest.

Setup:
    pip install azure-storage-blob

Auth (pick one — set in .env or environment):
    AZURE_STORAGE_CONNECTION_STRING   full connection string (easiest)
    -- OR --
    AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY

Required:
    AZURE_BLOB_CONTAINER   container name that holds the sop/ blobs

Usage:
    python data/download_sops.py
    python data/download_sops.py --out ./sops --csv ./sop.csv --dry-run
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path


def _get_client(container: str):
    from azure.storage.blob import BlobServiceClient

    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if conn_str:
        return BlobServiceClient.from_connection_string(conn_str).get_container_client(container)

    account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
    if account and key:
        url = f"https://{account}.blob.core.windows.net"
        return BlobServiceClient(account_url=url, credential=key).get_container_client(container)

    sys.exit(
        "ERROR: set AZURE_STORAGE_CONNECTION_STRING "
        "or AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY"
    )


def _safe_name(sop_id: str, name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return f"{sop_id} - {clean}.docx"


def download(csv_path: str, out_dir: str, container: str, dry_run: bool = False) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    client = None if dry_run else _get_client(container)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Found {len(rows)} SOPs in {csv_path}")
    ok = skipped = errors = 0

    for row in rows:
        sop_id = row["SOPId"].strip()
        name = row["Name"].strip()
        blob_path = row["LatestBlob"].strip()
        dest = out / _safe_name(sop_id, name)

        if dest.exists():
            print(f"  [skip]  {dest.name}")
            skipped += 1
            continue

        if dry_run:
            print(f"  [dry]   {blob_path} -> {dest.name}")
            ok += 1
            continue

        try:
            data = client.download_blob(blob_path).readall()
            dest.write_bytes(data)
            print(f"  [ok]    {dest.name}  ({len(data):,} bytes)")
            ok += 1
        except Exception as exc:
            print(f"  [ERROR] {blob_path}: {exc}", file=sys.stderr)
            errors += 1

    print(f"\nDone — downloaded: {ok}, skipped: {skipped}, errors: {errors}")


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass

    _here = Path(__file__).parent
    p = argparse.ArgumentParser(description="Download SOP blobs from Azure")
    p.add_argument("--csv", default=str(_here / "sop.csv"), help="path to sop.csv manifest")
    p.add_argument("--out", default=str(_here / "sops"), help="local output directory")
    p.add_argument(
        "--container",
        default=os.getenv("AZURE_BLOB_CONTAINER", ""),
        help="Azure blob container name (or set AZURE_BLOB_CONTAINER)",
    )
    p.add_argument("--dry-run", action="store_true", help="print plan without downloading")
    args = p.parse_args()

    if not args.dry_run and not args.container:
        sys.exit("ERROR: --container or AZURE_BLOB_CONTAINER required")

    download(args.csv, args.out, args.container, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
