"""Country list and matching of source country names to ISO-3166 countries.

Every source file spells country names differently ("USA", "United States",
"United States of America"). All names are resolved to an ISO alpha-3 code,
which is the stable key of the `country` table.
"""

import re
import unicodedata

import pandas as pd

# Kosovo has no official ISO-3166 entry and is therefore missing from
# countries-extended.csv, but it is part of every World Happiness Report.
# XK / XKX are the user-assigned codes used by the EU, the World Bank and others.
EXTRA_COUNTRIES = [
    {
        "name": "Kosovo", "alpha_2": "XK", "alpha_3": "XKX", "code": None,
        "iso_3166_2": None, "region": "Europe", "subregion": "Southern Europe",
        "intermediate_region": None, "region_code": 150, "subregion_code": 39,
        "intermediate_region_code": None,
    },
]

# Source name -> ISO alpha-3 code, for names that differ from the ISO name.
# Started from COUNTRY_NAME_MAPPING in code/bina_db.py, but mapped to ISO codes
# instead of the names of the old hand-edited database. Two entries of the old
# mapping were wrong and are corrected here: both Congos were merged into one
# "Congo", and "Somalia" was mapped to "Somaliland region".
ALIASES = {
    "Bolivia": "BOL",
    "British Virgin Islands": "VGB",
    "Brunei": "BRN",
    "Cape Verde": "CPV",
    "Congo (Brazzaville)": "COG",
    "Congo, Rep.": "COG",
    "Congo (Kinshasa)": "COD",
    "Congo, Dem. Rep.": "COD",
    "Democratic Republic of Congo": "COD",
    "Czech Republic": "CZE",
    "East Timor": "TLS",
    "Eswatini, Kingdom of": "SWZ",
    "Swaziland": "SWZ",
    "Faeroe Islands": "FRO",
    "Hong Kong S.A.R. of China": "HKG",
    "Hong Kong S.A.R., China": "HKG",
    "Hong Kong, China": "HKG",
    "Iran": "IRN",
    "Ivory Coast": "CIV",
    "Kosovo": "XKX",
    "Kyrgyz Republic": "KGZ",
    "Lao": "LAO",
    "Laos": "LAO",
    "Macao, China": "MAC",
    "Macedonia": "MKD",
    "Micronesia, Fed. Sts.": "FSM",
    "Moldova": "MDA",
    "North Korea": "PRK",
    "South Korea": "KOR",
    "Palestine": "PSE",
    "Palestinian Territories": "PSE",
    "State of Palestine": "PSE",
    "Russia": "RUS",
    "Slovak Republic": "SVK",
    "St. Kitts and Nevis": "KNA",
    "St. Lucia": "LCA",
    "St. Martin (French part)": "MAF",
    "St. Vincent and the Grenadines": "VCT",
    "Syria": "SYR",
    "Taiwan": "TWN",
    "Tanzania": "TZA",
    "Turkiye": "TUR",
    "UAE": "ARE",
    "UK": "GBR",
    "United Kingdom": "GBR",
    "USA": "USA",
    "United States": "USA",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
}

# Names that are deliberately NOT mapped, because they are not (or no longer)
# ISO countries. Mapping them to a neighbour would create duplicate values
# (e.g. "North Cyprus" and "Cyprus" in the same year).
NOT_A_COUNTRY = {
    "North Cyprus", "Northern Cyprus", "Somaliland", "Somaliland region",
    "Somaliland Region", "Channel Islands", "Netherlands Antilles",
    "Czechoslovakia", "East Germany", "West Germany", "USSR", "Yugoslavia",
    "Serbia and Montenegro", "xx",
}


def normalize_name(name):
    """Lower-case ASCII form of a name, used for tolerant comparisons."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = name.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def load_countries(path):
    """Reads the ISO-3166 list (countries-extended.csv) and adds EXTRA_COUNTRIES."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    countries = pd.DataFrame({
        "name": raw["name"],
        "alpha_2": raw["alpha-2"],
        "alpha_3": raw["alpha-3"],
        "code": raw["country-code"],
        "iso_3166_2": raw["iso_3166-2"],
        "region": raw["region"],
        "subregion": raw["sub-region"],
        "intermediate_region": raw["intermediate-region"],
        "region_code": raw["region-code"],
        "subregion_code": raw["sub-region-code"],
        "intermediate_region_code": raw["intermediate-region-code"],
    })
    countries = pd.concat([countries, pd.DataFrame(EXTRA_COUNTRIES)], ignore_index=True)
    # Empty strings -> NULL, numeric codes -> int
    countries = countries.replace({"": None})
    for column in ["code", "region_code", "subregion_code", "intermediate_region_code"]:
        countries[column] = pd.to_numeric(countries[column]).astype("Int64")
    return countries


class CountryMatcher:
    """Resolves source country names (or alpha-3 codes) to ISO alpha-3 codes."""

    def __init__(self, countries):
        self.alpha_3_codes = set(countries["alpha_3"])
        self.by_name = {normalize_name(n): a3 for n, a3 in zip(countries["name"], countries["alpha_3"])}
        self.by_alias = {normalize_name(n): a3 for n, a3 in ALIASES.items()}
        self.ignored = {normalize_name(n) for n in NOT_A_COUNTRY}

    def match(self, name, code=None):
        """Returns the alpha-3 code, or None if the name cannot be resolved."""
        if isinstance(code, str) and code in self.alpha_3_codes:
            return code
        key = normalize_name(name)
        if key in self.ignored:
            return None
        return self.by_alias.get(key) or self.by_name.get(key)
