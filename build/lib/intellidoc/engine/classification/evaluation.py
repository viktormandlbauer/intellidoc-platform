"""Evaluate against a labelled folder: <dir>/<label>/*.pdf.

Reports accuracy, per-class precision/recall/F1, a confusion matrix, expected calibration
error, and an accuracy-vs-coverage table that tells you where to put `classification.min_confidence`.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ...contracts.results import ClassificationResult
from ..pipeline import DocumentPipeline

THRESHOLDS = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]


@dataclass
class Sample:
    path: Path
    truth: str


def collect_samples(root: Path) -> list[Sample]:
    samples = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        for pdf in sorted(sub.rglob("*")):
            if pdf.is_file() and pdf.suffix.lower() == ".pdf":
                samples.append(Sample(pdf, sub.name))
    return samples


def _ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    if not pairs:
        return 0.0
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for conf, ok in pairs:
        buckets[min(int(conf * bins), bins - 1)].append((conf, ok))
    total = len(pairs)
    ece = 0.0
    for items in buckets.values():
        avg_conf = sum(c for c, _ in items) / len(items)
        acc = sum(ok for _, ok in items) / len(items)
        ece += len(items) / total * abs(avg_conf - acc)
    return ece


def evaluate(
    pipeline: DocumentPipeline,
    root: Path,
    out_dir: Path,
    progress: Callable[[int, int, ClassificationResult], None] | None = None,
) -> dict:
    samples = collect_samples(root)
    if not samples:
        raise SystemExit(f"no PDFs found in sub-folders of {root} (expected <dir>/<label>/*.pdf)")

    known = set(pipeline.settings.classification.labels())
    unknown = sorted({s.truth for s in samples} - known)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as fh:
        for i, s in enumerate(samples, 1):
            r = pipeline.process_file(s.path)
            rec = {"truth": s.truth, "correct": r.label == s.truth, **r.to_dict()}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)
            if progress:
                progress(i, len(samples), r)

    scored = [r for r in rows if r["label"] is not None and r["confidence"] is not None]
    n = len(rows)
    correct = sum(r["correct"] for r in rows)

    labels = sorted(known | {r["truth"] for r in rows})
    cm: dict[str, Counter] = {t: Counter() for t in labels}
    for r in rows:
        cm[r["truth"]][r["label"] or "∅"] += 1

    per_class = {}
    for lab in labels:
        tp = cm[lab][lab]
        fp = sum(cm[t][lab] for t in labels if t != lab)
        fn = sum(cm[lab].values()) - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
        per_class[lab] = {"precision": p, "recall": rc, "f1": f1, "support": tp + fn}

    sweep = []
    for t in THRESHOLDS:
        kept = [r for r in scored if r["confidence"] >= t]
        sweep.append({
            "threshold": t,
            "coverage": len(kept) / n if n else 0.0,
            "accuracy": (sum(r["correct"] for r in kept) / len(kept)) if kept else None,
            "n": len(kept),
        })

    summary = {
        "samples": n,
        "accuracy": correct / n if n else 0.0,
        "no_prediction": n - len(scored),
        "ece": _ece([(r["confidence"], r["correct"]) for r in scored]),
        "mean_ms": sum(r["elapsed_ms"] for r in rows) / n if n else 0.0,
        "unknown_folder_labels": unknown,
        "per_class": per_class,
        "threshold_sweep": sweep,
        "confusion": {t: dict(c) for t, c in cm.items()},
        "model": rows[0]["model"] if rows else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "report.md").write_text(render_report(summary, labels), encoding="utf-8")
    return summary


def render_report(s: dict, labels: list[str]) -> str:
    L = []
    L.append("# Classification evaluation\n")
    L.append(f"- Model: `{s['model']}`")
    L.append(f"- Samples: {s['samples']}  ·  no prediction (no text / errors): {s['no_prediction']}")
    L.append(f"- **Accuracy: {s['accuracy']:.1%}**")
    L.append(f"- Expected calibration error (lower is better): {s['ece']:.3f}")
    L.append(f"- Mean time per PDF: {s['mean_ms']:.0f} ms")
    if s["unknown_folder_labels"]:
        L.append(f"- ⚠ Folders that are not labels in the config (always wrong): {', '.join(s['unknown_folder_labels'])}")

    L.append("\n## Accuracy vs. coverage\n")
    L.append("Pick `classification.min_confidence` where accuracy is acceptable; coverage is the share handled automatically.\n")
    L.append("| min_confidence | coverage | accuracy | n |")
    L.append("|---:|---:|---:|---:|")
    for row in s["threshold_sweep"]:
        acc = "–" if row["accuracy"] is None else f"{row['accuracy']:.1%}"
        L.append(f"| {row['threshold']:.2f} | {row['coverage']:.1%} | {acc} | {row['n']} |")

    L.append("\n## Per class\n")
    L.append("| label | precision | recall | F1 | support |")
    L.append("|---|---:|---:|---:|---:|")
    for lab in labels:
        m = s["per_class"][lab]
        L.append(f"| {lab} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['support']} |")

    cols = labels + ["∅"]
    L.append("\n## Confusion matrix (rows = truth, columns = predicted)\n")
    L.append("| truth \\ pred | " + " | ".join(cols) + " |")
    L.append("|---|" + "---:|" * len(cols))
    for t in labels:
        if not sum(s["confusion"][t].values()):
            continue
        L.append(f"| **{t}** | " + " | ".join(str(s["confusion"][t].get(c, 0) or "") for c in cols) + " |")
    return "\n".join(L) + "\n"
