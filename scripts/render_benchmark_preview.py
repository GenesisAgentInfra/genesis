"""Render README design previews. Every number is invented, not an eval result.

Run from any directory with Python 3.12+: python scripts/render_benchmark_preview.py
Visual reference: https://artificialanalysis.ai/agents/coding-agents
No third-party logos, chart assets, benchmark data, or web fonts are bundled.
"""

from html import escape
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "assets" / "readme"
MOCK = {
    "Genesis": {"quality": 82, "time": 74, "cost": 0.32, "color": "#8050ef"},
    "Cursor": {"quality": 61, "time": 52, "cost": 0.46, "color": "#397fe9"},
    "Claude Code": {"quality": 68, "time": 96, "cost": 0.58, "color": "#bf8166"},
    "Codex": {"quality": 57, "time": 83, "cost": 0.27, "color": "#222222"},
}
METRICS = [
    ("quality", "Impact Detection", "Higher is better", 100, "#8050ef"),
    ("time", "Analysis Time", "Wall time in seconds · Lower is better", 120, "#f3de41"),
    ("cost", "Analysis Cost", "API cost in USD · Lower is better", 0.75, "#f18a40"),
]


def label(x, y, value, size=16, color="#202020", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>'
        f"{escape(str(value))}</text>"
    )


def card(x, y, width, metric):
    key, title, subtitle, maximum, accent = metric
    out = [
        f'<g transform="translate({x} {y})">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="409" rx="8" '
        'fill="white" stroke="#dcdcdc"/>',
        f'<rect x="18" y="26" width="16" height="16" fill="{accent}"/>',
        label(42, 43, title, 28, extra='font-family="Georgia, Times New Roman, serif"'),
        label(18, 74, subtitle, 13, "#777777"),
        label(18, 94, "MOCK DATA · NOT MEASURED", 12, "#777777"),
    ]
    left, right, top, bottom = 35, width - 22, 121, 309
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        grid_y = bottom - fraction * (bottom - top)
        out.append(
            f'<path d="M {left} {grid_y} H {right}" stroke="#dedede" stroke-dasharray="2 4"/>'
        )
    ranked = sorted(MOCK, key=lambda name: MOCK[name][key], reverse=key == "quality")
    step = (right - left) / len(ranked)
    bar_width = step * 0.72
    for i, name in enumerate(ranked):
        row = MOCK[name]
        value = row[key]
        height = value / maximum * (bottom - top)
        center = left + step * (i + 0.5)
        value_label = f"${value:.2f}" if key == "cost" else str(value)
        out.extend(
            [
                f'<rect x="{center - bar_width / 2:.2f}" y="{bottom - height:.2f}" '
                f'width="{bar_width:.2f}" height="{height:.2f}" rx="4" '
                f'fill="{row["color"]}"/>',
                label(
                    round(center, 2),
                    round(bottom - height - 9, 2),
                    value_label,
                    17,
                    extra='text-anchor="middle"',
                ),
                label(
                    0,
                    0,
                    name,
                    16,
                    extra=f'transform="translate({center + 5:.2f} 329) rotate(-48)" '
                    'text-anchor="end"',
                ),
            ]
        )
    out.append("</g>")
    return "\n".join(out)


def render(mobile=False):
    width, height = (430, 1394) if mobile else (1200, 538)
    title = "Agent Change Benchmarks"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{title} — mock data, not measured</title>',
        '<desc id="desc">Design preview with fictional impact-detection scores, analysis time, and API cost '
        "for Genesis, Cursor, Claude Code, and Codex. These numbers are not benchmark "
        "results and do not establish a performance ranking.</desc>",
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="Arial, Helvetica, sans-serif">',
        label(
            20,
            42,
            title,
            30 if mobile else 34,
            extra='font-family="Georgia, Times New Roman, serif"',
        ),
        label(20, 69, "Know what changes before you ship.", 15, "#777777"),
    ]
    for i, metric in enumerate(METRICS):
        parts.append(
            card(
                20 if mobile else 20 + i * 392,
                91 + i * 426 if mobile else 91,
                390 if mobile else 376,
                metric,
            )
        )
    parts.extend(["</g>", "</svg>", ""])
    return "\n".join(parts)


if __name__ == "__main__":
    for is_mobile in (False, True):
        suffix = "-mobile" if is_mobile else ""
        (DEST / f"agent-change-benchmarks{suffix}.svg").write_text(render(is_mobile))
