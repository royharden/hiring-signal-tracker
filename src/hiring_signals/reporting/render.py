"""Deterministic public JSON/Markdown/HTML/SVG from one closed release boundary."""

import hashlib
import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from hiring_signals import contracts as c
from hiring_signals.shared.aggregate_privacy import models as p

from .population import Closed, Method, PublicMonth, Scope

ASSETS = ("aggregates.json", "aggregates.md", "trends.svg", "report.html")
MAX_ASSET_BYTES = 2 * 1024 * 1024


class ReportWindow(Closed):
    schema_version: c.Version
    month_ids: Annotated[tuple[c.Month, ...], Field(min_length=4, max_length=4)]
    method: Method
    source_scope: Scope
    quality_status: Literal["not_measured"]
    months: Annotated[tuple[PublicMonth, ...], Field(max_length=4)]

    @model_validator(mode="after")
    def window(self) -> Self:
        numbers = [int(month[:4]) * 12 + int(month[5:]) for month in self.month_ids]
        if any(right != left + 1 for left, right in zip(numbers, numbers[1:], strict=False)):
            raise ValueError("four consecutive ordered months required")
        seen = set()
        for month in self.months:
            if month.month not in self.month_ids or month.month in seen:
                raise ValueError("duplicate or outside-window month")
            if month.method != self.method or month.source_scope != self.source_scope:
                raise ValueError("mixed method/sample-population scope")
            seen.add(month.month)
        return self


class Point(Closed):
    month: c.Month
    state: Literal["observed", "suppressed", "partial", "failed", "not_run", "not_provided"]
    share: p.Share | None
    change_pp: Annotated[float, Field(ge=-100, le=100, allow_inf_nan=False)] | None
    version_sha256: c.Digest | None
    policy: p.Policy | None


def _window(value) -> ReportWindow:
    try:
        return ReportWindow.model_validate(value)
    except (ValidationError, TypeError):
        raise ValueError("invalid_closed_report_input") from None


def series(window: ReportWindow, metric: p.Metric, label: p.ClassLabel) -> tuple[Point, ...]:
    window = _window(window)
    if metric not in c.FIELD_IDS or label not in p.class_inventory(metric):
        raise ValueError("unsupported field/class series")
    indexed = {month.month: month for month in window.months}
    result = []
    for month_id in window.month_ids:
        month = indexed.get(month_id)
        share, version, policy, state = None, None, None, "not_provided"
        if month is not None:
            version = month.version_sha256
            policy = month.policy
            if month.method_status == "not_run":
                state = "not_run"
            elif month.source_coverage == "failed":
                state = "failed"
            elif month.source_coverage == "partial" or month.method_status == "partial":
                state = "partial"
            else:
                part = next(part for part in month.partitions if part.metric == metric)
                if part.trend_eligible:
                    share = next(cell.share for cell in part.cells if cell.label == label)
                    state = "observed"
                else:
                    state = "suppressed"
        change = None
        if (
            result
            and share is not None
            and result[-1].share is not None
            and result[-1].version_sha256 == version
            and result[-1].policy == policy
        ):
            change = (share - result[-1].share) * 100
        result.append(
            Point(
                month=month_id,
                state=state,
                share=share,
                change_pp=change,
                version_sha256=version,
                policy=policy,
            )
        )
    return tuple(result)


def _pretty(value):
    return value.replace("skills.", "Skill: ").replace("_", " ").capitalize()


def _scope(scope):
    return {
        "population_predictions": "Population prediction estimates",
        "original_synthetic_population": "Original synthetic population predictions",
        "gold_sample": "Gold sample predictions — sample estimates, not population trends",
    }[scope]


def _released_rows(window):
    indexed = {month.month: month for month in window.months}
    for month_id in window.month_ids:
        month = indexed.get(month_id)
        if month is None:
            yield (month_id, "—", "—", "—", "—", "not provided")
        elif month.method_status == "not_run":
            yield (month_id, "—", "—", "—", "—", "not run")
        else:
            for part in month.partitions:
                public = p.format_projection(part, "table")
                for cell in public["cells"]:
                    count = "—" if cell["numerator"] is None else str(cell["numerator"])
                    denominator = (
                        "—" if public["denominator"] is None else str(public["denominator"])
                    )
                    share = "—" if cell["share"] is None else f"{cell['share'] * 100:.2f}%"
                    state = "suppressed" if public["suppressed"] else public["coverage"]
                    yield (
                        month_id,
                        _pretty(part.metric),
                        _pretty(cell["label"]),
                        f"{count}/{denominator}",
                        share,
                        state,
                    )


def _bindings(window):
    return [
        f"{month.month}: policy={month.policy}; version={month.version_sha256}; "
        f"method={month.method}; scope={month.source_scope}"
        for month in window.months
    ]


def render_markdown(window: ReportWindow) -> str:
    window = _window(window)
    lines = [
        "# Hiring signal trends",
        "",
        _scope(window.source_scope),
        "",
        f"Method: {window.method}. Prediction quality: not measured.",
        *(_bindings(window) or ["No monthly release supplied."]),
        "",
        "Rates use the admitted monthly cohort, including unavailable/error outcomes.",
        "Small cells and siblings are withheld. Incomplete months are not complete trends.",
        "No accuracy, human-agreement, cost or uncertainty measurement is supplied.",
        "",
        "| Month | Field | Class | Count / eligible N | Share | Coverage |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in _released_rows(window))
    return "\n".join(lines) + "\n"


def render_svg(window: ReportWindow) -> str:
    window = _window(window)
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": "0 0 900 540",
            "role": "img",
            "aria-labelledby": "chart-title chart-desc",
        },
    )
    ET.SubElement(root, "title", {"id": "chart-title"}).text = "Four-month hiring prediction shares"
    ET.SubElement(root, "metadata").text = json.dumps(
        {"method": window.method, "scope": window.source_scope, "bindings": _bindings(window)},
        sort_keys=True,
    )
    ET.SubElement(root, "desc", {"id": "chart-desc"}).text = (
        _scope(window.source_scope)
        + ". Quality not measured. Hidden or incomplete points are gaps, never zero."
    )
    ET.SubElement(root, "rect", {"width": "900", "height": "540", "fill": "#ffffff"})
    for chart, metric in enumerate(("ai_engineering_role", "portfolio_requested")):
        top, baseline, height = 38 + chart * 260, 213 + chart * 260, 150
        ET.SubElement(
            root,
            "text",
            {
                "x": "65",
                "y": str(top),
                "font-size": "18",
                "font-family": "sans-serif",
                "fill": "#17243a",
            },
        ).text = _pretty(metric)
        for percent in (0, 50, 100):
            y = baseline - percent / 100 * height
            ET.SubElement(
                root,
                "line",
                {"x1": "80", "x2": "825", "y1": str(y), "y2": str(y), "stroke": "#dce4ee"},
            )
            ET.SubElement(
                root,
                "text",
                {
                    "x": "68",
                    "y": str(y + 4),
                    "text-anchor": "end",
                    "font-size": "11",
                    "font-family": "sans-serif",
                },
            ).text = f"{percent}%"
        points = series(window, metric, "positive")
        previous = None
        for index, point in enumerate(points):
            x = 110 + index * 225
            ET.SubElement(
                root,
                "text",
                {
                    "x": str(x),
                    "y": str(baseline + 23),
                    "text-anchor": "middle",
                    "font-size": "12",
                    "font-family": "sans-serif",
                },
            ).text = point.month
            if point.share is None:
                ET.SubElement(
                    root,
                    "text",
                    {
                        "x": str(x),
                        "y": str(baseline + 41),
                        "text-anchor": "middle",
                        "font-size": "10",
                        "font-family": "sans-serif",
                        "fill": "#66758b",
                    },
                ).text = point.state.replace("_", " ")
                previous = None
                continue
            y = baseline - point.share * height
            if previous is not None and point.change_pp is not None:
                ET.SubElement(
                    root,
                    "line",
                    {
                        "x1": str(previous[0]),
                        "y1": str(previous[1]),
                        "x2": str(x),
                        "y2": str(y),
                        "stroke": "#2563eb",
                        "stroke-width": "3",
                        "data-role": "observed-segment",
                    },
                )
            circle = ET.SubElement(
                root,
                "circle",
                {
                    "cx": str(x),
                    "cy": str(y),
                    "r": "5",
                    "fill": "#2563eb",
                    "data-role": "observed-point",
                },
            )
            ET.SubElement(circle, "title").text = f"{point.month}: {point.share * 100:.2f}%"
            previous = (x, y)
    return ET.tostring(root, encoding="unicode") + "\n"


def render_html(window: ReportWindow) -> str:
    window = _window(window)
    rows = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
        for row in _released_rows(window)
    )
    scope = html.escape(_scope(window.source_scope))
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Hiring signal trends</title><style>"
        "body{font:16px system-ui,sans-serif;color:#17243a;background:#f4f7fb;margin:0}"
        "main{max-width:1100px;margin:3rem auto;padding:0 1.5rem}"
        "h1{font-size:2.5rem;margin-bottom:.4rem}"
        ".card{background:white;border:1px solid #dce4ee;border-radius:14px;"
        "padding:1.5rem;margin:1.5rem 0}"
        ".notice{border-left:4px solid #2563eb;padding:1rem;background:#eaf1ff}"
        "svg{width:100%;height:auto}table{width:100%;border-collapse:collapse;font-size:.9rem}"
        "th,td{text-align:left;padding:.6rem;border-bottom:1px solid #e5eaf2}th{background:#edf2f9}"
        ".scroll{overflow:auto}a{color:#1d4ed8}footer{color:#66758b;margin:2rem 0}"
        "</style></head><body><main><h1>Hiring signal trends</h1>"
        f"<p>{scope} · {html.escape(window.method)}</p>"
        + "<p>"
        + "<br>".join(html.escape(value) for value in _bindings(window))
        + "</p>"
        + "<div class='notice'><strong>Prediction quality has not been measured.</strong> "
        "No accuracy, human-agreement, cost or uncertainty estimate is supplied. "
        "Rates include unavailable/error outcomes in the admitted monthly denominator. "
        "Small cells and all complementary siblings are withheld. "
        "Incomplete or suppressed points remain gaps.</div>"
        f"<section class='card'>{render_svg(window)}</section>"
        "<section class='card'><h2>Released monthly fields</h2><p>Only the closed released "
        "projection is shown. A dash is withheld or unavailable, never an invented zero.</p>"
        "<div class='scroll'><table><thead><tr><th>Month</th><th>Field</th><th>Class</th>"
        "<th>Count / eligible N</th><th>Share</th><th>Coverage</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></section>"
        "<p><a href='aggregates.json'>Released JSON</a> · <a href='aggregates.md'>Markdown</a> · "
        "<a href='trends.svg'>SVG chart</a></p><footer>Single-partition suppression is bounded: "
        "it does not establish anonymity or solve every cross-release correlation.</footer>"
        "</main></body></html>\n"
    )


def _assets(window: ReportWindow) -> dict[str, str]:
    window = _window(window)
    return {
        "aggregates.json": window.model_dump_json(indent=2) + "\n",
        "aggregates.md": render_markdown(window),
        "trends.svg": render_svg(window),
        "report.html": render_html(window),
    }


class FileDigest(Closed):
    name: Literal["aggregates.json", "aggregates.md", "trends.svg", "report.html"]
    sha256: c.Digest


class ReportManifest(Closed):
    schema_version: c.Version
    window_sha256: c.Digest
    files: Annotated[tuple[FileDigest, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def closure(self) -> Self:
        if tuple(file.name for file in self.files) != ASSETS:
            raise ValueError("exact report asset closure required")
        if self.window_sha256 != self.files[0].sha256:
            raise ValueError("window digest must bind actual JSON bytes")
        return self


def export_report(window: ReportWindow, destination: Path) -> ReportManifest:
    """New explicit destination only; manifest last marks a complete local bundle.

    A failed/crashed write can leave an unsealed directory; verify_report refuses
    it. Existing targets/files are never overwritten or recursively removed.
    """
    assets = _assets(window)
    manifest = ReportManifest(
        schema_version=1,
        window_sha256=hashlib.sha256(assets[ASSETS[0]].encode()).hexdigest(),
        files=tuple(
            FileDigest(name=name, sha256=hashlib.sha256(assets[name].encode()).hexdigest())
            for name in ASSETS
        ),
    )
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    for name, value in assets.items():
        with (destination / name).open("xb") as handle:
            handle.write(value.encode("utf-8"))
    with (destination / "manifest.json").open("xb") as handle:
        handle.write((manifest.model_dump_json(indent=2) + "\n").encode())
    return manifest


def verify_report(directory: Path) -> ReportWindow:
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.stat().st_size > MAX_ASSET_BYTES
    ):
        raise ValueError("report manifest unavailable")
    try:
        manifest = ReportManifest.model_validate_json(manifest_path.read_bytes())
    except ValidationError:
        raise ValueError("invalid_closed_report_manifest") from None
    actual = {}
    for file in manifest.files:
        path = directory / file.name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError("report asset unavailable or over bound")
        value = path.read_bytes()
        if hashlib.sha256(value).hexdigest() != file.sha256:
            raise ValueError("report asset digest differs")
        actual[file.name] = value
    try:
        window = ReportWindow.model_validate_json(actual["aggregates.json"])
    except ValidationError:
        raise ValueError("invalid_closed_report_json") from None
    expected = {name: value.encode() for name, value in _assets(window).items()}
    if actual != expected:
        raise ValueError("report assets differ from closed released projection")
    return window
