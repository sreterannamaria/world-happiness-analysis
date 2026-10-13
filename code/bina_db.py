"""Gemeinsame Hilfsfunktionen für die Notebooks: DB-Verbindung und Länder-Lookup.

Die Zugangsdaten werden aus Umgebungsvariablen gelesen (siehe .env.example),
damit keine Passwörter im Code stehen.
"""

import os

import mariadb


def connect():
    """Baut eine Verbindung zur MariaDB-Datenbank auf (autocommit aus)."""
    try:
        connection = mariadb.connect(
            user=os.environ.get("BINA_DB_USER", "root"),
            password=os.environ["BINA_DB_PASSWORD"],
            host=os.environ.get("BINA_DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("BINA_DB_PORT", "3306")),
            database=os.environ.get("BINA_DB_NAME", "bina"),
        )
    except KeyError:
        raise RuntimeError("Umgebungsvariable BINA_DB_PASSWORD ist nicht gesetzt (siehe .env.example).")

    connection.autocommit = False
    return connection


# Unterschiedliche Ländernamen in den Quelldaten -> Name in der Tabelle «country»
COUNTRY_NAME_MAPPING = {
    "North Cyprus": "Cyprus",
    "Northern Cyprus": "Cyprus",
    "Congo (Kinshasa)": "Congo",
    "Congo (Brazzaville)": "Congo",
    "Congo, Dem. Rep.": "Congo",
    "Congo, Rep.": "Congo",
    "Democratic Republic of Congo": "Congo",
    "Somalia": "Somaliland region",
    "Somaliland": "Somaliland region",
    "Taiwan Province of China": "Taiwan",
    "Hong Kong S.A.R., China": "Hong Kong",
    "Hong Kong S.A.R. of China": "Hong Kong",
    "Hong Kong, China": "Hong Kong",
    "Trinidad & Tobago": "Trinidad and Tobago",
    "North Macedonia": "Macedonia",
    "Czechia": "Czech Republic",
    "Eswatini, Kingdom of": "Eswatini",
    "UK": "United Kingdom",
    "Lao": "Laos",
    "Macao, China": "Macao",
    "Slovak Republic": "Slovakia",
    "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Palestine": "Palestinian Territories",
    "Palestine/West Bank": "Palestinian Territories",
    "Palestine/Gaza": "Palestinian Territories",
    "USA": "United States",
    "UAE": "United Arab Emirates",
    "Brunei": "Brunei Darussalam",
    "Micronesia, Fed. Sts.": "Micronesia (Federated States of)",
    "Cape Verde": "Cabo Verde",
    "Kyrgyz Republic": "Kyrgyzstan",
    "St. Lucia": "Saint Lucia",
    "St. Kitts and Nevis": "Saint Kitts and Nevis",
    "Faeroe Islands": "Faroe Islands",
    "St. Martin (French part)": "Saint Martin (French part)",
    "Yemen People's Republic": "Yemen",
    "Yemen Arab Republic": "Yemen",
    "Republic of Vietnam": "Vietnam",
    "Democratic Republic of Vietnam": "Vietnam",
    "East Timor": "Timor-Leste",
}


def map_country_name(country_name):
    return COUNTRY_NAME_MAPPING.get(country_name, country_name)


class CountryLookup:
    """Sucht die ID eines Landes in der Tabelle «country» und cached das Ergebnis."""

    def __init__(self, connection):
        self.connection = connection
        self.cache = dict()

    def lookup(self, country_name):
        mapped_country_name = map_country_name(country_name)

        if mapped_country_name not in self.cache:
            cursor = self.connection.cursor()
            cursor.execute("select id from country where name=?", (mapped_country_name,))
            row = cursor.fetchone()
            self.cache[mapped_country_name] = row[0] if row else None

        return self.cache[mapped_country_name]


def get_or_create_metric_definition(connection, name, description=None):
    """Gibt die ID der Metrikdefinition zurück und legt sie bei Bedarf an."""
    cursor = connection.cursor()
    cursor.execute("select id from metric_definition where name=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("insert into metric_definition(name, description) values (?, ?)", (name, description))
    connection.commit()
    return cursor.lastrowid
