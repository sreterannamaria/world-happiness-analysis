"""Tests for the parts of the pipeline that can break silently."""

import math
import sqlite3

import pytest

from pipeline import DATA_DIR
from pipeline.build_database import build, map_metric_name, parse_value, read_whr
from pipeline.countries import CountryMatcher, load_countries


# --- value conversion -------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("12k", 12_000),
    ("12.1k", 12_100),
    ("3.4M", 3_400_000),
    ("1.25M", 1_250_000),
    ("6.48B", 6_480_000_000),
    ("−0.5", -0.5),        # Unicode minus sign
    ("−1.2k", -1_200),
    ("-4.99", -4.99),
    ("7.587", 7.587),
    (3.5, 3.5),
])
def test_parse_value(raw, expected):
    assert parse_value(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "N/A", None, float("nan"), "abc"])
def test_parse_value_missing(raw):
    assert math.isnan(parse_value(raw))


# --- metric names across years ----------------------------------------------

@pytest.mark.parametrize("column, has_explained, expected", [
    ("Family", False, "Social support"),                                # 2015-2017
    ("Social support", False, "Social support"),                        # 2018-2019 (contribution)
    ("Social support", True, None),                                     # 2020+ raw value, ignored
    ("Explained by: Social support", True, "Social support"),
    ("Economy..GDP.per.Capita.", False, "Economy (GDP per Capita)"),    # 2017
    ("Logged GDP per capita", True, None),
    ("Explained by: Log GDP per capita", True, "Economy (GDP per Capita)"),
    ("Explained by: GDP per capita", True, "Economy (GDP per Capita)"),  # 2022
    ("Perceptions of corruption", True, None),
    ("Trust..Government.Corruption.", False, "Trust (Government Corruption)"),
    ("Ladder score", True, "Happiness Score"),
    ("Happiness score", True, "Happiness Score"),
    ("Score", False, "Happiness Score"),
    ("Dystopia (1.83) + residual", True, "Dystopia Residual"),
    ("Happiness Rank", False, None),
    ("Standard Error", False, None),
])
def test_map_metric_name(column, has_explained, expected):
    assert map_metric_name(column, has_explained) == expected


@pytest.mark.parametrize("year", range(2015, 2024))
def test_every_whr_year_has_all_factors(year):
    metrics = set(read_whr(year)["metric"])
    assert {"Happiness Score", "Economy (GDP per Capita)", "Social support", "Health (Life Expectancy)",
            "Freedom", "Trust (Government Corruption)", "Generosity"} <= metrics


def test_whr_2015_is_the_genuine_report():
    data = read_whr(2015)
    scores = data[data["metric"] == "Happiness Score"].set_index("country_name")["value"]
    assert len(scores) == 158
    assert scores["Switzerland"] == pytest.approx(7.587)
    assert scores["Iceland"] == pytest.approx(7.561)
    assert scores["Denmark"] == pytest.approx(7.527)


# --- country matching -------------------------------------------------------

@pytest.fixture(scope="module")
def matcher():
    return CountryMatcher(load_countries(DATA_DIR / "supplemental" / "countries-extended.csv"))


@pytest.mark.parametrize("name, expected", [
    ("Congo (Kinshasa)", "COD"),
    ("Congo (Brazzaville)", "COG"),
    ("Congo, Dem. Rep.", "COD"),
    ("Congo, Rep.", "COG"),
    ("Somalia", "SOM"),
    ("Taiwan Province of China", "TWN"),
    ("Hong Kong S.A.R., China", "HKG"),
    ("Ivory Coast", "CIV"),
    ("Côte d'Ivoire", "CIV"),
    ("Trinidad & Tobago", "TTO"),
    ("Macedonia", "MKD"),
    ("North Macedonia", "MKD"),
    ("Swaziland", "SWZ"),
    ("Eswatini, Kingdom of", "SWZ"),
    ("Czech Republic", "CZE"),
    ("Czechia", "CZE"),
    ("South Korea", "KOR"),
    ("North Korea", "PRK"),
    ("UK", "GBR"),
    ("United States", "USA"),
    ("Turkiye", "TUR"),
    ("Kosovo", "XKX"),
    ("Palestinian Territories", "PSE"),
    ("Lao", "LAO"),
])
def test_country_matching(matcher, name, expected):
    assert matcher.match(name) == expected


def test_country_matching_prefers_codes(matcher):
    assert matcher.match("Some unknown spelling", "CHE") == "CHE"
    assert matcher.match("Kosovo", "OWID_KOS") == "XKX"  # non-ISO code falls back to the name


@pytest.mark.parametrize("name", ["North Cyprus", "Northern Cyprus", "Somaliland region", "USSR", "xx"])
def test_non_countries_stay_unmatched(matcher, name):
    assert matcher.match(name) is None


# --- built database ---------------------------------------------------------

@pytest.fixture(scope="module")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "bina.sqlite"
    build(path, verbose=False)
    connection = sqlite3.connect(path)
    yield connection
    connection.close()


def test_database_has_happiness_scores(database):
    counts = dict(database.execute(
        "select m.year, count(distinct m.country) from metric m "
        "join metric_definition d on d.id = m.metric_definition "
        "where d.name = 'Happiness Score' group by m.year").fetchall())
    for year in range(2015, 2020):
        assert counts[year] >= 140, year


def test_database_tables(database):
    assert database.execute("select count(*) from country").fetchone()[0] == 250  # 249 ISO + Kosovo
    assert database.execute("select count(*) from metric_definition").fetchone()[0] == 18
    assert database.execute("select count(*) from metric where value is null").fetchone()[0] == 0
