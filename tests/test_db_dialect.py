from app.db_dialect import is_mysql_family, normalize_database_url


def test_is_mysql_family_supports_mariadb() -> None:
    assert is_mysql_family("mysql")
    assert is_mysql_family("mysql+pymysql")
    assert is_mysql_family("mariadb")
    assert is_mysql_family("mariadbconnector")
    assert not is_mysql_family("sqlite")


def test_normalize_database_url_accepts_mariadb_scheme() -> None:
    assert (
        normalize_database_url("mariadb://user:pass@localhost:3306/energy_db")
        == "mysql+pymysql://user:pass@localhost:3306/energy_db"
    )


def test_normalize_database_url_accepts_mysql_scheme_without_driver() -> None:
    assert (
        normalize_database_url("mysql://user:pass@localhost:3306/energy_db")
        == "mysql+pymysql://user:pass@localhost:3306/energy_db"
    )
