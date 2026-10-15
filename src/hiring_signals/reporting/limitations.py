"""Limitations from closed released scalars only, without evaluator/source access."""

from . import render


def sample_limitations(window):
    """Deterministic prose from the released schema only, with no private cohort sizes."""
    window = render.ReportWindow.model_validate(window)
    if window.source_scope != "gold_sample" or window.method != "rules":
        raise ValueError("closed_rules_sample_window_required")
    supplied = {month.month: month for month in window.months}
    lines = [
        "# Sample report limitations",
        "",
        "Scope: sample predictions; sample estimates, not population trends.",
        "Method: rules. Prediction quality, human agreement and live model cost: not measured.",
        "No Gold labels, accuracy metrics, source IDs or raw posting text are in this projection.",
        "Missing, partial and suppressed points are gaps, never invented zero observations.",
        "No threshold fitting, calibration, bootstrap or heldout evidence is supplied here.",
        "Closed report bytes alone do not establish source origin, rights or Human labeling.",
        "Synthetic labels do not establish human Gold, source rights or representative samples.",
        "Single-partition suppression does not establish anonymity or repeated-release safety.",
        "This is a local artifact; external publication requires its own authorization.",
        "",
        "| Month | Processing | Release policy | Reported denominator |",
        "|---|---|---|---|",
    ]
    for month_id in window.month_ids:
        month = supplied.get(month_id)
        if month is None:
            lines.append(f"| {month_id} | not_provided | NA | withheld |")
        else:
            denominator = (
                str(month.eligible_denominator)
                if month.eligible_denominator is not None
                else "withheld"
            )
            lines.append(f"| {month_id} | {month.method_status} | {month.policy} | {denominator} |")
    return "\n".join(lines) + "\n"
