from ingest.download import build_file_list, download_file


def test_file_list_has_six_months_and_zone_lookup():
    names = [name for _, name in build_file_list()]
    assert len(names) == 7
    assert names[0] == "yellow_tripdata_2024-01.parquet"
    assert names[5] == "yellow_tripdata_2024-06.parquet"
    assert names[6] == "taxi_zone_lookup.csv"


def test_existing_non_empty_file_is_skipped(tmp_path):
    dest = tmp_path / "already_here.parquet"
    dest.write_bytes(b"data")
    # The URL is never opened because the file already exists.
    assert download_file("http://invalid.invalid/x", dest) is False
