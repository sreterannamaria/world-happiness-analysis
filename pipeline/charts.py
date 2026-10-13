"""Chart helpers (matplotlib). All charts are written as PNG files."""

import matplotlib

matplotlib.use("Agg")  # no display needed

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from .build_database import ADDITIONAL_METRICS, HAPPINESS_SCORE, POLITICAL_SYSTEM, WHR_METRICS  # noqa: E402

# Categorical palette, validated for colour-vision deficiencies (adjacent pairs).
# Colours are assigned in this fixed order; text labels next to every line
# make sure identity never depends on colour alone.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

# Diverging blue <-> red with a neutral grey midpoint for correlation heatmaps
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_grey_red", ["#104281", "#3987e5", "#cde2fb", "#f0efec", "#f6c9c4", "#e34948", "#8f1d1c"])

# Fixed order of all indicators (WHR factors first), used for colour assignment
INDICATOR_ORDER = ([m for m in WHR_METRICS if m != HAPPINESS_SCORE]
                   + [name for name, _ in ADDITIONAL_METRICS.values()] + [POLITICAL_SYSTEM[0]])

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK_SECONDARY,
    "axes.titlecolor": INK,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "savefig.dpi": 150,
})


def _title(fig, ax, title, subtitle):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=28 + 12 * subtitle.count("\n"))
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_SECONDARY, va="bottom")


def _spread(positions, min_gap):
    """Moves label positions (sorted ascending) apart so they are at least min_gap apart."""
    result = list(positions)
    for i in range(1, len(result)):
        result[i] = max(result[i], result[i - 1] + min_gap)
    return result


def _clean_axes(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def ranking_chart(corr, scope, years, top, path, weakest=False):
    """Bump chart: rank of the factors that were among the `top` strongest (or weakest) in any year."""
    data = corr[(corr["scope"] == scope) & (corr["year"].isin(years))].copy()
    if weakest:
        data["rank"] = data.groupby("year")["abs_r"].rank(ascending=True, method="first").astype(int)
    shown = data.loc[data["rank"] <= top, "indicator"].unique()
    shown = [name for name in INDICATOR_ORDER if name in shown]
    data = data[data["indicator"].isin(shown)]
    years = sorted(data["year"].unique())
    max_rank = int(data["rank"].max())

    fig, ax = plt.subplots(figsize=(9, 0.45 * max_rank + 2.6))
    ax.axhspan(0.5, top + 0.5, color="#f0efec", zorder=0)  # the "top N" band
    labels = []
    for i, indicator in enumerate(shown):
        color = PALETTE[i % len(PALETTE)]
        series = data[data["indicator"] == indicator].set_index("year")["rank"].reindex(years)
        ax.plot(series.index, series.values, color=color, linewidth=2, zorder=2)
        ax.scatter(series.index, series.values, s=70, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
        last_year = series.last_valid_index()
        text = indicator if last_year == years[-1] else f"{indicator} (until {last_year})"
        labels.append((series[last_year], text, color))

    # Direct labels in the right margin, next to each factor's last rank
    labels.sort()
    for y, (_, text, color) in zip(_spread([label[0] for label in labels], 0.7), labels):
        ax.text(years[-1] + 0.45, y, "\u25CF " + text, va="center", fontsize=9, color=INK)
        ax.text(years[-1] + 0.45, y, "\u25CF", va="center", fontsize=9, color=color)

    ax.set_xticks(years)
    ax.set_xlim(min(years) - 0.4, max(years) + 0.4)
    ax.set_ylim(max_rank + 0.5, 0.5)
    ax.set_yticks(range(1, max_rank + 1))
    ax.set_ylabel("Weakest rank (1 = weakest)" if weakest else "Rank (1 = strongest)")
    ax.tick_params(length=0)
    _clean_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)

    which = "weakest" if weakest else "strongest"
    _title(fig, ax, f"{scope}: the {which} factors of happiness, {years[0]}–{years[-1]}",
           f"Ranked by absolute Pearson correlation with the Happiness Score.\n"
           f"Shown: every factor among the {top} {which} in at least one year (shaded band).")
    fig.subplots_adjust(left=0.08, right=0.66, top=1 - 1.25 / fig.get_figheight(), bottom=0.1)
    fig.savefig(path)
    plt.close(fig)


def heatmap(table, scope, year, path):
    """Lower-triangle correlation matrix with metric names as labels."""
    columns = [HAPPINESS_SCORE] + [c for c in INDICATOR_ORDER if c in table.columns]
    matrix = table[columns].corr()
    mask = np.triu(np.ones_like(matrix, dtype=bool), k=1)
    values = np.ma.array(matrix.values, mask=mask)

    size = 0.62 * len(columns) + 3
    fig, ax = plt.subplots(figsize=(size + 1.5, size))
    image = ax.imshow(values, cmap=DIVERGING, vmin=-1, vmax=1)
    for (i, j), value in np.ndenumerate(matrix.values):
        if not mask[i, j] and not np.isnan(value):
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7.5,
                    color="white" if abs(value) > 0.6 else INK)
    ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right")
    ax.set_yticks(range(len(columns)), columns)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, shrink=0.6, pad=0.02)
    colorbar.set_label("Pearson r")
    colorbar.outline.set_visible(False)
    _title(fig, ax, f"{scope}: correlation matrix, {year}",
           f"{len(table)} countries with a Happiness Score; missing values excluded pairwise.")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def cluster_chart(clusters, centers, explained_variance, year, path):
    """Scatter plot of the countries on the first two principal components, coloured by cluster."""
    markers = ["o", "s", "^"]
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for i, cluster in enumerate(sorted(clusters["cluster"].unique())):
        members = clusters[clusters["cluster"] == cluster]
        label = (f"Cluster {cluster}: {len(members)} countries, "
                 f"mean score {members['happiness_score'].mean():.2f}")
        ax.scatter(members["pc1"], members["pc2"], s=36, marker=markers[i], color=PALETTE[i],
                   edgecolor=SURFACE, linewidth=0.8, label=label, zorder=2)
    ax.scatter(centers["pc1"], centers["pc2"], marker="X", s=160, color=INK, edgecolor=SURFACE,
               linewidth=1.5, label="Cluster centre", zorder=3)

    # Label the three happiest and the three least happy countries; the labels are
    # stacked next to the points with thin leader lines so they never overlap
    ranked = clusters.sort_values("happiness_score", ascending=False)
    gap = 0.05 * (clusters["pc2"].max() - clusters["pc2"].min())
    for group, dx in ((ranked.head(3), 0.08), (ranked.tail(3), 0.08)):
        group = group.sort_values("pc2")
        for (country, row), y in zip(group.iterrows(), _spread(group["pc2"], gap)):
            ax.annotate(country, (row["pc1"], row["pc2"]), xytext=(group["pc1"].max() + dx, y),
                        fontsize=8, color=INK_SECONDARY, va="center",
                        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.6})

    ax.set_xlabel(f"Principal component 1 ({explained_variance[0]:.0%} of variance)")
    ax.set_ylabel(f"Principal component 2 ({explained_variance[1]:.0%} of variance)")
    ax.grid(color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(length=0)
    _clean_axes(ax)
    ax.legend(frameon=False, loc="best", fontsize=9)
    _title(fig, ax, f"Countries clustered by all indicators, {year}",
           "PCA (2 components) of min-max scaled indicators, then K-Means with k = 3. "
           "Clusters numbered by mean Happiness Score.")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
