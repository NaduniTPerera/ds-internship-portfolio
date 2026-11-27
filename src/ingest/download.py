"""Download NYC TLC Yellow Taxi trip data (Jan-Jun 2024) and the taxi zone lookup.

Usage (from the repo root):
    uv run python -m ingest.download

Behaviour:
- Files that already exist in data/raw with size > 0 are skipped.
- Each file is downloaded to "<name>.part" first and renamed only when complete,
  so an interrupted download never looks like a finished file.
- After download the file size is checked; an empty file is an error.
"""

import logging
import shutil
import sys
import urllib.request
from pathlib import Path

from ds_intern.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)

BASE_URL = "https://d37ci6vzurychx.cloudfront.net"
YEAR = 2024
MONTHS = range(1, 7)  # January to June
TIMEOUT_SECONDS = 60
CHUNK_SIZE = 1024 * 1024  # 1 MB


def build_file_list() -> list[tuple[str, str]]:
    """Return (url, filename) pairs for every file to download."""
    files = []
    for month in MONTHS:
        name = f"yellow_tripdata_{YEAR}-{month:02d}.parquet"
        files.append((f"{BASE_URL}/trip-data/{name}", name))
    files.append((f"{BASE_URL}/misc/taxi_zone_lookup.csv", "taxi_zone_lookup.csv"))
    return files


def human_size(num_bytes: int) -> str:
    """Format a byte count as KB or MB for log messages."""
    if num_bytes < 1_000_000:
        return f"{num_bytes / 1e3:.1f} KB"
    return f"{num_bytes / 1e6:.1f} MB"


def download_file(url: str, dest: Path) -> bool:
    """Download url to dest. Return True if downloaded, False if skipped."""
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("Skip %s (already exists, %s)", dest.name, human_size(dest.stat().st_size))
        return False

    tmp = dest.with_name(dest.name + ".part")
    logger.info("Downloading %s", url)
    request = urllib.request.Request(url, headers={"User-Agent": "ds-intern-downloader"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            with open(tmp, "wb") as out:
                shutil.copyfileobj(response, out, CHUNK_SIZE)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    size = tmp.stat().st_size
    if size == 0:
        tmp.unlink()
        raise ValueError(f"Downloaded file is empty: {url}")

    tmp.replace(dest)
    logger.info("Saved %s (%s)", dest.name, human_size(size))
    return True


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = skipped = failed = 0
    for url, name in build_file_list():
        try:
            if download_file(url, RAW_DATA_DIR / name):
                downloaded += 1
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            logger.error("Failed %s: %s", name, exc)

    logger.info("Done: %d downloaded, %d skipped, %d failed", downloaded, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
