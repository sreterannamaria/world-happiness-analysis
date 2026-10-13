"""Correlation analysis, rankings, heatmaps and PCA/K-Means clustering.

Reads bina.sqlite (built by pipeline.build_database) and writes all results
to results/.

    python -m pipeline.analyze
"""

import json
import sqlite3

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import MinMaxScaler

from . import DB_PATH, RESULTS_DIR
from . import charts
from .build_database import DYSTOPIA_RESIDUAL, HAPPINESS_SCORE

YEARS = list(range(2015, 2024))
# Years of the case study. From 2020 on several additional indicators end
# (material footprint, sustainable development index), so the weakest-factor
# ranking is only comparable within 2015-2019.
CASE_STUDY_YEARS = list(range(2015, 2020))
SCOPES = ["World", "Africa", "Americas", "Asia", "Europe"]  # ISO "region" column; Oceania has too few countries
MIN_COUNTRIES = 15  # minimum number of countries with both values for a correlation
REPRESENTATIVE_YEAR = 2019  # last year before the pandemic with (almost) all indicators
N_CLUSTERS = 3
RANDOM_STATE = 42

# Not used as explanatory factors: the score itself and the Dystopia residual
# (the part of the score the WHR model does not explain).
EXCLUDED = {HAPPINESS_SCORE, DYSTOPIA_RESIDUAL}


def load_values(db_path=DB_PATH):
    """All metric values with country name and region, as a long table."""
    with sqlite3.connect(db_path) as connection:
        return pd.read_sql(
            "select c.alpha_3, c.name as country, c.region, m.year, d.name as metric, m.value "
            "from metric m join country c on c.id = m.country "
            "join metric_definition d on d.id = m.metric_definition "
            "where m.year between ? and ?", connection, params=(min(YEARS), max(YEARS)))


def country_table(values, year, scope="World"):
    """Country x metric table for one year, limited to countries with a Happiness Score."""
    data = values[values["year"] == year]
    if scope != "World":
        data = data[data["region"] == scope]
    table = data.pivot_table(index="country", columns="metric", values="value")
    if HAPPINESS_SCORE not in table.columns:
        return table.iloc[0:0]
    return table[table[HAPPINESS_SCORE].notna()]


def correlations(values):
    """Pearson r of every indicator with the Happiness Score per scope and year.

    Missing values are excluded pairwise (the original notebooks filled them
    with 0, which distorts the correlations). An indicator is only ranked if at
    least MIN_COUNTRIES countries have both values. Rank 1 = strongest absolute
    correlation.
    """
    rows = []
    for scope in SCOPES:
        for year in YEARS:
            table = country_table(values, year, scope)
            for indicator in table.columns:
                if indicator in EXCLUDED:
                    continue
                pair = table[[HAPPINESS_SCORE, indicator]].dropna()
                if len(pair) < MIN_COUNTRIES or pair[indicator].nunique() < 2:
                    continue
                r = pair[HAPPINESS_SCORE].corr(pair[indicator])
                rows.append({"scope": scope, "year": year, "indicator": indicator,
                             "r": r, "abs_r": abs(r), "n_countries": len(pair)})
    result = pd.DataFrame(rows)
    result["rank"] = (result.groupby(["scope", "year"])["abs_r"]
                      .rank(ascending=False, method="first").astype(int))
    return result.sort_values(["scope", "year", "rank"]).reset_index(drop=True)


def pca_kmeans(values, year):
    """PCA (2 components) and K-Means (k=3) of all countries for one year."""
    table = country_table(values, year).drop(columns=[c for c in EXCLUDED if c != HAPPINESS_SCORE],
                                             errors="ignore")
    # Keep indicators that at least 80% of the countries have; fill the remaining
    # gaps with the median (the original notebooks used 0).
    table = table.loc[:, table.notna().mean() >= 0.8]
    features = SimpleImputer(strategy="median").fit_transform(table)
    features = MinMaxScaler().fit_transform(features)  # same scaling as the original notebook

    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    components = pca.fit_transform(features)
    kmeans = KMeans(n_clusters=N_CLUSTERS, n_init=10, random_state=RANDOM_STATE).fit(components)

    result = pd.DataFrame(components, index=table.index, columns=["pc1", "pc2"])
    result["happiness_score"] = table[HAPPINESS_SCORE]
    # Number clusters by mean happiness (1 = happiest) so the labels are stable
    order = result.assign(c=kmeans.labels_).groupby("c")["happiness_score"].mean().sort_values(ascending=False)
    relabel = {old: new for new, old in enumerate(order.index, start=1)}
    result["cluster"] = [relabel[label] for label in kmeans.labels_]
    centers = pd.DataFrame(kmeans.cluster_centers_, columns=["pc1", "pc2"], index=[relabel[i] for i in range(N_CLUSTERS)])
    return result, centers.sort_index(), list(table.columns), pca.explained_variance_ratio_


def summary(corr, clusters, features, explained_variance, values):
    def factors(group):
        return [{"indicator": row.indicator, "r": round(row.r, 3), "n_countries": int(row.n_countries)}
                for row in group.itertuples()]

    scopes = {}
    for (scope, year), group in corr.groupby(["scope", "year"]):
        n_countries = len(country_table(values, year, scope))
        weakest = group.sort_values("abs_r").head(3)
        scopes.setdefault(scope, {})[str(year)] = {
            "countries_with_happiness_score": n_countries,
            "top3": factors(group.head(3)),
            "bottom3": factors(weakest),
        }
    return {
        "method": {
            "correlation": "Pearson r with the Happiness Score, pairwise complete countries",
            "ranking": "by absolute correlation, 1 = strongest",
            "min_countries_per_correlation": MIN_COUNTRIES,
            "excluded_from_ranking": sorted(EXCLUDED),
            "continents": "ISO-3166 region column (data/supplemental/countries-extended.csv)",
        },
        "scopes": scopes,
        "pca_kmeans": {
            "year": REPRESENTATIVE_YEAR,
            "features": features,
            "explained_variance_ratio": [round(v, 3) for v in explained_variance],
            "clusters": {
                str(c): {
                    "countries": int((clusters["cluster"] == c).sum()),
                    "mean_happiness_score": round(clusters.loc[clusters["cluster"] == c, "happiness_score"].mean(), 3),
                }
                for c in sorted(clusters["cluster"].unique())
            },
        },
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    values = load_values()

    corr = correlations(values)
    corr.round(4).to_csv(RESULTS_DIR / "correlations.csv", index=False)

    for scope in SCOPES:
        charts.ranking_chart(corr, scope, YEARS, top=3,
                             path=RESULTS_DIR / f"ranking-top3-{scope.lower()}.png")
    charts.ranking_chart(corr, "World", CASE_STUDY_YEARS, top=3, weakest=True,
                         path=RESULTS_DIR / "ranking-bottom3-world.png")

    for scope in SCOPES:
        table = country_table(values, REPRESENTATIVE_YEAR, scope)
        table = table.drop(columns=[c for c in EXCLUDED if c != HAPPINESS_SCORE], errors="ignore")
        table = table.loc[:, table.notna().sum() >= MIN_COUNTRIES]
        charts.heatmap(table, scope, REPRESENTATIVE_YEAR,
                       path=RESULTS_DIR / f"heatmap-{scope.lower()}-{REPRESENTATIVE_YEAR}.png")

    clusters, centers, features, explained = pca_kmeans(values, REPRESENTATIVE_YEAR)
    clusters.round(4).sort_values(["cluster", "happiness_score"], ascending=[True, False]) \
        .to_csv(RESULTS_DIR / f"pca-kmeans-{REPRESENTATIVE_YEAR}.csv")
    charts.cluster_chart(clusters, centers, explained, REPRESENTATIVE_YEAR,
                         path=RESULTS_DIR / f"pca-kmeans-{REPRESENTATIVE_YEAR}.png")

    with open(RESULTS_DIR / "summary.json", "w", encoding="utf-8") as file:
        json.dump(summary(corr, clusters, features, explained, values), file, indent=2, ensure_ascii=False)

    print_findings(corr)
    print(f"\nResults written to {RESULTS_DIR}")


def print_findings(corr):
    print("Strongest factors (rank by |r|):")
    for scope in SCOPES:
        print(f"  {scope}")
        for year in YEARS:
            group = corr[(corr["scope"] == scope) & (corr["year"] == year)]
            if group.empty:
                continue
            top = ", ".join(f"{row.indicator} ({row.r:+.2f})" for row in group.head(3).itertuples())
            print(f"    {year}: {top}")
    print("Weakest factors, World:")
    for year in CASE_STUDY_YEARS:
        group = corr[(corr["scope"] == "World") & (corr["year"] == year)].sort_values("abs_r")
        print(f"    {year}: " + ", ".join(f"{row.indicator} ({row.r:+.2f})" for row in group.head(3).itertuples()))


if __name__ == "__main__":
    main()
