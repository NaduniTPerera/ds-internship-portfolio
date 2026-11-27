from ds_intern.config import PROJECT_ROOT, database_url


def test_project_root_has_pyproject():
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_database_url_uses_psycopg():
    assert database_url().startswith("postgresql+psycopg://")
