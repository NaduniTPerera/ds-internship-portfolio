from quality.run_checks import EXIT_ERROR, EXIT_FAILED, EXIT_PASSED, main
from tests.helpers import trip, trips_df


def write_month(raw_dir, bad_rows: int, good_rows: int) -> None:
    rows = [trip() for _ in range(good_rows)] + [trip(fare_amount=-5.0) for _ in range(bad_rows)]
    trips_df(rows).to_parquet(raw_dir / "yellow_tripdata_2024-01.parquet")


def test_exit_codes_follow_the_threshold(tmp_path):
    write_month(tmp_path, bad_rows=1, good_rows=9)   # 10% of rows fail
    args = ["--month", "2024-01", "--raw-dir", str(tmp_path)]

    assert main([*args, "--max-failure-pct", "20"]) == EXIT_PASSED
    assert main([*args, "--max-failure-pct", "10"]) == EXIT_PASSED   # equal = pass
    assert main([*args, "--max-failure-pct", "5"]) == EXIT_FAILED


def test_missing_file_or_bad_threshold_is_an_error(tmp_path):
    assert main(["--month", "2024-01", "--max-failure-pct", "5",
                 "--raw-dir", str(tmp_path)]) == EXIT_ERROR
    assert main(["--month", "2024-01", "--max-failure-pct", "150"]) == EXIT_ERROR


def test_json_output(tmp_path):
    write_month(tmp_path, bad_rows=0, good_rows=3)
    out = tmp_path / "result.json"
    main(["--month", "2024-01", "--max-failure-pct", "1", "--raw-dir", str(tmp_path),
          "--json", str(out)])
    text = out.read_text(encoding="utf-8")
    assert '"passed": true' in text
    assert '"rows_failing": 0' in text
