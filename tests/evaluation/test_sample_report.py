"""Original bounded projection/CLI controls; no independent DEV dataset execution."""

import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest
import test_domain as h
import test_workflow as wiring

from hiring_signals import cli
from hiring_signals.evaluation import domain, sample_report
from hiring_signals.reporting import render
from hiring_signals.shared.aggregate_privacy import models as privacy

MONTHS = ("2026-07", "2026-08", "2026-09", "2026-10")


def issued(count=1):
    authority = h.SourceAuthority()
    items = []
    for number in range(count):
        # Repeated original syntax is a numeric suppression control, not a corpus.
        item, _ = h.item("Requirements: Python", sources=authority)
        pin = item.pin.model_copy(
            update={"item_id": hashlib.sha256(str(number).encode()).hexdigest()}
        )
        item, _ = h.item("Requirements: Python", pin=pin, sources=authority)
        items.append(item)
    registry = domain.ExecutionRegistry(tuple(items), authority)
    adapter = domain.HiringDomainAdapter(registry)
    runner = domain.HiringMethodRunner(registry, "rules", config_sha256=h.H)
    predictions = tuple(
        runner.predict(adapter.to_public_input(h.gold(item), registry.source_view(h.gold(item))))
        for item in items
    )
    return registry, tuple(item.pin.item_id for item in items), predictions


def test_small_sample_withholds_cohort_and_all_cells_while_empty_months_are_gaps():
    """Catches a small sample becoming public counts or missing months becoming zero trends."""
    registry, ids, predictions = issued()
    window = sample_report.build(
        registry, expected_item_ids=ids, predictions=predictions, month_ids=MONTHS
    )
    assert window.source_scope == "gold_sample" and len(window.months) == 1
    month = window.months[0]
    assert month.eligible_denominator is None and len(month.partitions) == 37
    assert all(
        cell.numerator is None and cell.share is None
        for part in month.partitions
        for cell in part.cells
    )
    points = render.series(window, "skills.python", "positive")
    assert [point.state for point in points] == ["not_provided"] * 3 + ["suppressed"]
    assert all(point.share is None and point.change_pp is None for point in points)
    limitation = sample_report.limitations(window)
    assert "withheld" in limitation and "not population trends" in limitation
    assert ids[0] not in limitation + window.model_dump_json()
    assert "Requirements: Python" not in limitation + window.model_dump_json()


def test_explicit_v2_releases_supported_true_zero_without_relaxing_v1():
    """Catches local composition silently changing the canonical min-ten policy/default."""
    registry, ids, predictions = issued(10)
    default = sample_report.build(
        registry, expected_item_ids=ids, predictions=predictions, month_ids=MONTHS
    )
    explicit = sample_report.build(
        registry,
        expected_item_ids=ids,
        predictions=predictions,
        month_ids=MONTHS,
        policy=privacy.POLICY_V2,
    )
    assert render.series(default, "skills.python", "positive")[-1].state == "suppressed"
    assert render.series(explicit, "skills.python", "positive")[-1].share == 1
    assert render.series(explicit, "skills.python", "negative")[-1].share == 0
    assert explicit.months[0].eligible_denominator == 10


def test_missing_prediction_is_retained_as_failure_not_a_smaller_complete_sample():
    """Catches dropping expected IDs to improve reported coverage/processing state."""
    registry, ids, predictions = issued(2)
    window = sample_report.build(
        registry,
        expected_item_ids=ids,
        predictions=predictions[:1],
        month_ids=MONTHS,
        policy=privacy.POLICY_V2,
    )
    assert window.months[0].method_status == "partial"
    assert render.series(window, "skills.python", "positive")[-1].state == "partial"
    with pytest.raises(domain.DomainError, match="complete_requested_sample_population"):
        sample_report.build(
            registry, expected_item_ids=ids[:1], predictions=predictions[:1], month_ids=MONTHS
        )


@pytest.mark.parametrize("fault", ["duplicate", "changed", "source_stale", "window"])
def test_changed_or_stale_raw_issuance_does_not_gain_aggregate_authority(fault):
    """Catches forged/duplicate/stale records and out-of-window data crossing the release seam."""
    registry, ids, predictions = issued()
    months = MONTHS
    if fault == "duplicate":
        predictions = predictions + predictions
    elif fault == "changed":
        predictions = (predictions[0].model_copy(update={"config_sha256": "e" * 64}),)
    elif fault == "source_stale":
        registry.sources.remove(ids[0])
    else:
        months = ("2026-03", "2026-04", "2026-05", "2026-06")
    with pytest.raises(domain.DomainError):
        sample_report.build(
            registry, expected_item_ids=ids, predictions=predictions, month_ids=months
        )


def test_real_cli_optional_sample_bundle_and_limitations_use_only_closed_projection(
    tmp_path, monkeypatch
):
    """Catches private Gold/quality/source text copied into the public-safe sample artifacts."""
    options = wiring.inputs(tmp_path / "input")
    monkeypatch.setattr("socket.socket", lambda *a, **k: pytest.fail("network reached"))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(wiring.command(options) + ["--sample-months", *MONTHS])
    assert code == 0
    assert json.loads(output.getvalue())["sample_report"] == "local_closed_projection"
    directory = options["destination"]
    window = render.verify_report(directory / "sample-report")
    assert window.source_scope == "gold_sample"
    seal = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
    for name, pin in seal["files"].items():
        data = (directory / name).read_bytes()
        assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"]
    assert "sample-report/manifest.json" in seal["files"]
    assert "sample-limitations.md" in seal["files"]
    released = "".join(
        path.read_text(encoding="utf-8") for path in (directory / "sample-report").iterdir()
    )
    released += (directory / "sample-limitations.md").read_text(encoding="utf-8")
    for private in (
        "Requirements: Python",
        "a" * 64,
        "SYNTHETIC_PRIVATE_GOLD_PROVENANCE_CANARY",
        "end_to_end_accuracy",
        "accuracy_on_answered",
        "label_payload",
    ):
        assert private not in released
    # Limitations prose reproduces from the actual verified released JSON alone.
    assert (directory / "sample-limitations.md").read_text(encoding="utf-8") == (
        sample_report.limitations(window)
    )


@pytest.mark.parametrize(
    "months",
    [("2026-07", "2026-09", "2026-09", "2026-10"), ("2026-03", "2026-04", "2026-05", "2026-06")],
)
def test_bad_sample_window_refuses_before_method_or_output(tmp_path, monkeypatch, months):
    """Catches the optional report triggering execution before its fixed window is admitted."""
    options = wiring.inputs(tmp_path / "input")
    monkeypatch.setattr(wiring.w.rules, "classify", lambda *a: pytest.fail("rules reached"))
    error = io.StringIO()
    with contextlib.redirect_stderr(error):
        assert cli.main(wiring.command(options) + ["--sample-months", *months]) == 2
    assert json.loads(error.getvalue())["private_effects_possible"] is False
    assert not options["destination"].exists()


@pytest.mark.parametrize("interrupted_asset", ["report.html", "sample-limitations.md"])
def test_interrupted_sample_write_cannot_seal_or_overwrite_partial_artifacts(
    tmp_path, monkeypatch, interrupted_asset
):
    """Catches nested report interruption being called complete or overwritten on retry."""
    options = wiring.inputs(tmp_path / "input")
    original = Path.open

    def stopped(path, *args, **kwargs):
        if path.name == interrupted_asset and args and args[0] == "xb":
            raise KeyboardInterrupt()
        return original(path, *args, **kwargs)

    error = io.StringIO()
    with monkeypatch.context() as interrupted:
        interrupted.setattr(Path, "open", stopped)
        with contextlib.redirect_stderr(error):
            assert cli.main(wiring.command(options) + ["--sample-months", *MONTHS]) == 2
    assert json.loads(error.getvalue())["private_effects_possible"] is True
    directory = options["destination"]
    assert not (directory / "artifact-manifest.json").exists()
    before = {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }
    if interrupted_asset == "report.html":
        with pytest.raises(ValueError):
            render.verify_report(directory / "sample-report")
    else:
        assert render.verify_report(directory / "sample-report").source_scope == "gold_sample"
    with contextlib.redirect_stderr(io.StringIO()):
        assert cli.main(wiring.command(options) + ["--sample-months", *MONTHS]) == 2
    after = {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }
    assert before == after
