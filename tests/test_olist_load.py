from olist.load import TABLES, read_csv_as_text


def test_read_csv_keeps_text_nulls_newlines_and_strips_bom(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text(
        '﻿"zip","message","score"\n'
        '"01037",,5\n'
        '"14409","line one\nline two",4\n',
        encoding="utf-8",
        newline="\n",   # keep \n as-is (Windows would otherwise write \r\n)
    )
    table = read_csv_as_text(path)

    assert table.column_names == ["zip", "message", "score"]      # BOM removed
    assert table["zip"].to_pylist() == ["01037", "14409"]         # leading zero kept
    assert table["message"].to_pylist() == [None, "line one\nline two"]   # NULL + newline
    assert table["score"].to_pylist() == ["5", "4"]               # text; Postgres casts


def test_tables_are_in_foreign_key_order():
    order = list(TABLES)
    for parent, child in [("customers", "orders"), ("orders", "order_items"),
                          ("products", "order_items"), ("sellers", "order_items"),
                          ("orders", "order_payments"), ("orders", "order_reviews")]:
        assert order.index(parent) < order.index(child)
