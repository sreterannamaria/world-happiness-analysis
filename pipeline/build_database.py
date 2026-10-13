"""Builds bina.sqlite from the files in data/.

Same three tables as db/schema.sql (country, metric_definition, metric), but in
SQLite, so no database server is needed. The database is rebuilt from scratch
on every run.

    python -m pipeline.build_database
"""

import re
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd

from . import DATA_DIR, DB_PATH
from .countries import CountryMatcher, load_countries

WHR_YEARS = range(2015, 2024)

SCHEMA = """
CREATE TABLE country (
    id                       INTEGER PRIMARY KEY,
    name                     TEXT NOT NULL UNIQUE,
    alpha_2                  TEXT,
    alpha_3                  TEXT UNIQUE,
    code                     INTEGER,
    iso_3166_2               TEXT,
    region                   TEXT,
    subregion                TEXT,
    intermediate_region      TEXT,
    region_code              INTEGER,
    subregion_code           INTEGER,
    intermediate_region_code INTEGER
);
CREATE TABLE metric_definition (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);
CREATE TABLE metric (
    id                INTEGER PRIMARY KEY,
    value             REAL,
    year              INTEGER NOT NULL,
    country           INTEGER NOT NULL REFERENCES country (id),
    metric_definition INTEGER NOT NULL REFERENCES metric_definition (id),
    UNIQUE (year, country, metric_definition)
);
"""

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

HAPPINESS_SCORE = "Happiness Score"
DYSTOPIA_RESIDUAL = "Dystopia Residual"

WHR_METRICS = {
    HAPPINESS_SCORE: "Average answer to the Cantril ladder question (0 = worst, 10 = best possible life).",
    "Economy (GDP per Capita)": "WHR: part of the score explained by (log) GDP per capita.",
    "Social support": "WHR: part of the score explained by social support (called 'Family' in 2015-2017).",
    "Health (Life Expectancy)": "WHR: part of the score explained by healthy life expectancy.",
    "Freedom": "WHR: part of the score explained by freedom to make life choices.",
    "Trust (Government Corruption)": "WHR: part of the score explained by (absence of) perceived corruption.",
    "Generosity": "WHR: part of the score explained by generosity.",
    DYSTOPIA_RESIDUAL: "WHR: Dystopia benchmark plus the part of the score not explained by the six factors.",
}

# The ten additional indicators of the case study (chapter 2, "additional data").
# The two .xlsx files in data/additional/ ("Climate change as a threat" and
# "Surface Area") are not among them and were not used in the case study,
# so they are not loaded.
ADDITIONAL_METRICS = {
    "carbon_dioxide_consumption_per_country.csv": (
        "CO2 Emissions (Consumption)", "Consumption-based CO2 emissions of the country (total, in Mt)."),
    "cars_trucks_and_buses_per_1000_persons.csv": (
        "Cars, Trucks and Buses per 1000", "Motor vehicles per 1000 persons (data only for 2002-2007)."),
    "forest_area_square_kilometers.csv": (
        "Forest Area", "Forest area in square kilometres."),
    "homicide_per_100000.csv": (
        "Homicide Rate", "Homicides per 100,000 inhabitants (data up to 2016)."),
    "inflation_percentage.csv": (
        "Inflation", "Annual inflation in percent."),
    "material_footprint_per_capital.csv": (
        "Material Footprint", "Material footprint (source file says per capita; the values are country totals)."),
    "personal_integrity_and_security_index.csv": (
        "Personal Integrity and Security", "Personal integrity and security index."),
    "sustainable_development_index.csv": (
        "Sustainable Development Index", "Sustainable development index."),
    "urban_population_growth_percentage.csv": (
        "Urban Population Growth", "Annual growth of the urban population in percent."),
}
POLITICAL_SYSTEM = ("Political System", "0 = closed autocracy, 1 = electoral autocracy, "
                                        "2 = electoral democracy, 3 = liberal democracy.")


# ---------------------------------------------------------------------------
# Value conversion
# ---------------------------------------------------------------------------

_SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9}
_NUMBER = re.compile(r"^(-?\d+(?:\.\d+)?)\s*([kKmMbB]?)$")


def parse_value(value):
    """Converts source values like '12k', '3.4M', '1.2B' or '−0.5' to float (NaN if empty/invalid)."""
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    # Some sources use the Unicode minus sign (U+2212), which float() rejects
    text = str(value).strip().replace("−", "-")
    match = _NUMBER.match(text)
    if not match:
        return np.nan
    number, suffix = match.groups()
    return float(number) * _SUFFIXES.get(suffix.lower(), 1.0)


# ---------------------------------------------------------------------------
# World Happiness Report column names
# ---------------------------------------------------------------------------

# Column name variants per canonical metric (2015-2023 files).
_WHR_COLUMNS = {
    HAPPINESS_SCORE: ["Happiness Score", "Happiness.Score", "Score", "Ladder score", "Happiness score"],
    "Economy (GDP per Capita)": ["Economy (GDP per Capita)", "Economy..GDP.per.Capita.", "GDP per capita",
                                 "Explained by: Log GDP per capita", "Explained by: GDP per capita"],
    "Social support": ["Family", "Social support", "Explained by: Social support"],
    "Health (Life Expectancy)": ["Health (Life Expectancy)", "Health..Life.Expectancy.", "Healthy life expectancy",
                                 "Explained by: Healthy life expectancy"],
    "Freedom": ["Freedom", "Freedom to make life choices", "Explained by: Freedom to make life choices"],
    "Trust (Government Corruption)": ["Trust (Government Corruption)", "Trust..Government.Corruption.",
                                      "Perceptions of corruption", "Explained by: Perceptions of corruption"],
    "Generosity": ["Generosity", "Explained by: Generosity"],
    DYSTOPIA_RESIDUAL: ["Dystopia Residual", "Dystopia.Residual", "Dystopia + residual",
                        "Dystopia (1.83) + residual"],
}
_WHR_LOOKUP = {column: metric for metric, columns in _WHR_COLUMNS.items() for column in columns}
_WHR_COUNTRY_COLUMNS = ["Country", "Country name", "Country or region"]


def map_metric_name(column, file_has_explained_columns=False):
    """Maps a WHR column name to its canonical metric name, or None if the column is not used.

    One consistent definition across years: 2015-2019 only publish each factor's
    contribution to the score ("explained by"), not the raw survey values. From
    2020 on, the files contain both the raw values (e.g. "Logged GDP per capita",
    "Social support" as a 0-1 share) and the "Explained by: ..." contributions.
    We therefore use the "Explained by: ..." columns for 2020+ and ignore the raw
    ones. Note that in 2020+ a raw column has the same name as a 2018/2019
    contribution column ("Social support"), so the mapping depends on whether the
    file has "Explained by:" columns. Within one year a contribution is a positive
    linear transform of the raw value, so Pearson correlations are unaffected;
    for "Perceptions of corruption" it also keeps the sign the same as in
    2015-2019 (higher = more trust).
    """
    if file_has_explained_columns and column in _WHR_LOOKUP and not column.startswith("Explained by:"):
        # Raw value in a 2020+ file: only the score and the residual are taken as they are
        if _WHR_LOOKUP[column] not in (HAPPINESS_SCORE, DYSTOPIA_RESIDUAL):
            return None
    return _WHR_LOOKUP.get(column)


def read_whr(year):
    """Returns a long table (country_name, metric, value) for one WHR year."""
    # The files use comma, semicolon or tab as delimiter depending on the year
    data = pd.read_csv(DATA_DIR / "worldhappinessreport" / f"{year}.csv",
                       sep=None, engine="python", encoding="utf-8-sig")
    country_column = next(c for c in _WHR_COUNTRY_COLUMNS if c in data.columns)
    has_explained = any(c.startswith("Explained by:") for c in data.columns)

    frames = []
    for column in data.columns:
        metric = map_metric_name(column, has_explained)
        if metric is None:
            continue
        frames.append(pd.DataFrame({
            "country_name": data[country_column],
            "metric": metric,
            "value": data[column].map(parse_value),
        }))
    long = pd.concat(frames, ignore_index=True)
    long["year"] = year
    return long


def read_wide_indicator(file_name, metric):
    """Reads an additional indicator in wide format (country x year, ';' delimiter)."""
    data = pd.read_csv(DATA_DIR / "additional" / file_name, sep=";", encoding="utf-8-sig", dtype=str)
    long = data.melt(id_vars="country", var_name="year", value_name="raw")
    long["value"] = long["raw"].map(parse_value)
    long["year"] = long["year"].astype(int)
    long["metric"] = metric
    return long.rename(columns={"country": "country_name"})[["country_name", "metric", "value", "year"]]


def read_political_regime():
    """Reads political-regime.csv (long format: Entity, Code, Year, Political regime)."""
    data = pd.read_csv(DATA_DIR / "additional" / "political-regime.csv")
    return pd.DataFrame({
        "country_name": data["Entity"],
        "code": data["Code"],
        "metric": POLITICAL_SYSTEM[0],
        "value": data["Political regime"].astype(float),
        "year": data["Year"],
    })


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def resolve_countries(long, matcher, source, report):
    """Adds an alpha_3 column; collects unmatched names (and whether they have data since 2015)."""
    codes = long["code"] if "code" in long.columns else pd.Series(None, index=long.index)
    long = long.assign(alpha_3=[matcher.match(n, c) for n, c in zip(long["country_name"], codes)])
    unmatched = long[long["alpha_3"].isna()]
    for name, group in unmatched.groupby("country_name"):
        recent = bool(((group["year"] >= 2015) & group["value"].notna()).any())
        report[source].append((name, recent))
    return long.dropna(subset=["alpha_3"])


def build(db_path=DB_PATH, verbose=True):
    countries = load_countries(DATA_DIR / "supplemental" / "countries-extended.csv")
    matcher = CountryMatcher(countries)
    report = defaultdict(list)

    # 1. Read all sources into one long table
    frames = []
    for year in WHR_YEARS:
        frames.append(resolve_countries(read_whr(year), matcher, f"worldhappinessreport/{year}.csv", report))
    for file_name, (metric, _) in ADDITIONAL_METRICS.items():
        frames.append(resolve_countries(read_wide_indicator(file_name, metric), matcher,
                                        f"additional/{file_name}", report))
    frames.append(resolve_countries(read_political_regime(), matcher, "additional/political-regime.csv", report))
    values = pd.concat(frames, ignore_index=True).dropna(subset=["value"])

    # Two source names must never land on the same country, metric and year
    duplicates = values[values.duplicated(["alpha_3", "metric", "year"], keep=False)]
    if not duplicates.empty:
        raise ValueError("Duplicate values after country matching:\n"
                         + duplicates.sort_values(["metric", "year", "alpha_3"]).to_string())

    # 2. Write the database
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    connection.executescript(SCHEMA)

    countries = countries.astype(object).where(countries.notna(), None)
    countries.to_sql("country", connection, if_exists="append", index=False)
    country_ids = dict(connection.execute("select alpha_3, id from country").fetchall())

    definitions = list(WHR_METRICS.items()) + list(ADDITIONAL_METRICS.values()) + [POLITICAL_SYSTEM]
    connection.executemany("insert into metric_definition(name, description) values (?, ?)", definitions)
    metric_ids = dict(connection.execute("select name, id from metric_definition").fetchall())

    rows = zip(values["value"].astype(float), values["year"].astype(int),
               values["alpha_3"].map(country_ids), values["metric"].map(metric_ids))
    connection.executemany("insert into metric(value, year, country, metric_definition) values (?, ?, ?, ?)",
                           ((v, y, int(c), int(m)) for v, y, c, m in rows))
    connection.commit()

    if verbose:
        print_summary(connection, report)
    connection.close()


def print_summary(connection, report):
    count = connection.execute("select count(*) from metric").fetchone()[0]
    print(f"Wrote {count} values to {DB_PATH.name}")

    print("\nCountries with a Happiness Score per year:")
    for year, n in connection.execute(
            "select year, count(*) from metric m join metric_definition d on d.id = m.metric_definition "
            "where d.name = ? group by year order by year", (HAPPINESS_SCORE,)):
        print(f"  {year}: {n}")

    print("\nUnmatched country names per file (* = has values since 2015):")
    for source in sorted(report):
        names = sorted(report[source], key=lambda item: (not item[1], item[0]))
        recent = [f"{name}*" for name, has_recent in names if has_recent]
        older = [name for name, has_recent in names if not has_recent]
        text = ", ".join(recent)
        if older:
            text += (", " if text else "") + f"{len(older)} historical/without recent data"
        print(f"  {source}: {text}")


if __name__ == "__main__":
    build()
