import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from loom.models.taxonomy import Category, Sentiment, Urgency

INK_SECONDARY = "#52514E"
INK_MUTED = "#898781"
BORDER = "#DEDCD3"
GOOD = "#0CA30C"
WARNING = "#FAB219"
CRITICAL = "#D03B3B"

_CATEGORY_HUES = ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#4A3AA7", "#E34948"]
CATEGORY_COLOR = {category.value: _CATEGORY_HUES[i] for i, category in enumerate(Category)}
THEME_COLOR = CATEGORY_COLOR[Category.BILLING_PAYMENTS.value]  # var(--color-cat-1) equivalent

SENTIMENT_COLOR = {
    Sentiment.POSITIVE.value: GOOD,
    Sentiment.NEUTRAL.value: INK_MUTED,
    Sentiment.NEGATIVE.value: CRITICAL,
}
URGENCY_COLOR = {
    Urgency.HIGH.value: CRITICAL,
    Urgency.MEDIUM.value: WARNING,
    Urgency.LOW.value: GOOD,
}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "text.color": INK_SECONDARY,
    }
)


class ChartRenderer:
    """Renders the dashboard's matplotlib charts as PNG bytes for the PDF report."""

    @staticmethod
    def _png_bytes(fig) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", transparent=True)
        plt.close(fig)
        return buf.getvalue()

    def _horizontal_bar_chart(self, labels: list[str], values: list[int], bar_colors: list[str]) -> bytes:
        """Shared renderer for the category/theme/urgency bar charts: one bar per
        label, longest-first order preserved as given, value annotated at the tip.
        """
        height = max(1.4, 0.52 * len(labels) + 0.5)
        fig, ax = plt.subplots(figsize=(6.6, height))

        positions = list(range(len(labels)))
        bars = ax.barh(positions, values, color=bar_colors, height=0.62, zorder=3)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels, fontsize=10.5, color=INK_SECONDARY)
        ax.invert_yaxis()

        ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
        ax.get_xaxis().set_visible(False)
        ax.tick_params(left=False)

        max_value = max(values) if values else 1
        ax.set_xlim(0, max_value * 1.2 if max_value else 1)
        for bar, value in zip(bars, values, strict=True):
            ax.text(
                bar.get_width() + max_value * 0.02,
                bar.get_y() + bar.get_height() / 2,
                str(value),
                va="center",
                fontsize=9.5,
                color=INK_SECONDARY,
            )

        fig.tight_layout(pad=0.4)
        return self._png_bytes(fig)

    def category_distribution_chart(self, top_categories: list[dict]) -> bytes:
        labels = [c["name"] for c in top_categories]
        values = [c["count"] for c in top_categories]
        colors = [CATEGORY_COLOR.get(name, INK_MUTED) for name in labels]
        return self._horizontal_bar_chart(labels, values, colors)

    def theme_frequency_chart(self, top_themes: list[dict], top_n: int = 8) -> bytes:
        shown = top_themes[:top_n]
        labels = [t["name"] for t in shown]
        values = [t["count"] for t in shown]
        return self._horizontal_bar_chart(labels, values, [THEME_COLOR] * len(labels))

    def urgency_chart(self, urgency_distribution: dict[str, int]) -> bytes:
        labels = [u.value for u in Urgency]
        values = [urgency_distribution.get(label, 0) for label in labels]
        colors = [URGENCY_COLOR[label] for label in labels]
        return self._horizontal_bar_chart(labels, values, colors)

    def sentiment_chart(self, positive_pct: float, neutral_pct: float, negative_pct: float) -> bytes:
        """A single 100%-stacked horizontal bar, segment order Negative -> Neutral
        -> Positive, matching the dashboard's SentimentBar.
        """
        segments = [
            (Sentiment.NEGATIVE.value, negative_pct),
            (Sentiment.NEUTRAL.value, neutral_pct),
            (Sentiment.POSITIVE.value, positive_pct),
        ]

        fig, ax = plt.subplots(figsize=(6.6, 1.6))
        left = 0.0
        for name, pct in segments:
            ax.barh(
                0,
                pct,
                left=left,
                color=SENTIMENT_COLOR[name],
                height=0.5,
                edgecolor="white",
                linewidth=2,
                label=name,
            )
            if pct >= 8:
                ax.text(
                    left + pct / 2,
                    0,
                    f"{pct:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=10,
                    color="white",
                    fontweight="bold",
                )
            left += pct

        ax.set_xlim(0, 100)
        ax.set_ylim(-1, 1)
        ax.axis("off")
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.05),
            ncol=3,
            frameon=False,
            fontsize=9.5,
            labelcolor=INK_SECONDARY,
            handlelength=1.1,
            handleheight=1.1,
        )

        fig.tight_layout(pad=0.3)
        return self._png_bytes(fig)
