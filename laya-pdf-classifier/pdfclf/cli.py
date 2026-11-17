"""Command line: pdfclf classify | sort | evaluate | train | serve | index | search | ..."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import sys
from pathlib import Path

from .backends import BACKENDS, make_backend
from .classifier import STATUS_AUTO, PdfClassifier, Result
from .config import ConfigError, load_config


def _pdfs(paths: list[str], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            out += sorted(f for f in it if f.is_file() and f.suffix.lower() == ".pdf")
        elif p.is_file():
            out.append(p)
        else:
            print(f"skip: {p} not found", file=sys.stderr)
    return out


def _line(i: int, n: int, r: Result) -> None:
    conf = "  -  " if r.confidence is None else f"{r.confidence:.2f}"
    print(f"[{i:>4}/{n}] {r.status:<6} {str(r.label):<16} {conf}  {Path(r.file).name}", file=sys.stderr)


def _make(args) -> PdfClassifier:
    cfg = load_config(args.config)
    return PdfClassifier(cfg, make_backend(args.backend, cfg))


def cmd_classify(args) -> int:
    clf = _make(args)
    files = _pdfs(args.paths, args.recursive)
    results = []
    for i, f in enumerate(files, 1):
        r = clf.classify_file(f)
        results.append(r)
        _line(i, len(files), r)

    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".csv":
            rows = [r.to_row() for r in results]
            fields = sorted({k for row in rows for k in row}, key=lambda k: (k.startswith("q_"), k))
            base = ["file", "label", "confidence", "status"]
            fields = base + [f for f in fields if f not in base]
            with out.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
        else:
            with out.open("w", encoding="utf-8") as fh:
                for r in results:
                    fh.write(json.dumps(r.to_dict(include_text=args.with_text), ensure_ascii=False) + "\n")
        print(f"wrote {len(results)} results to {out}", file=sys.stderr)
    else:
        for r in results:
            print(json.dumps(r.to_dict(), ensure_ascii=False))
    _summary(results)
    return 0


def cmd_sort(args) -> int:
    clf = _make(args)
    files = _pdfs([args.source], args.recursive)
    dest = Path(args.dest)
    op = shutil.move if args.move else shutil.copy2
    results = []
    for i, f in enumerate(files, 1):
        r = clf.classify_file(f)
        results.append(r)
        folder = r.label if r.status == STATUS_AUTO else "_review"
        target_dir = dest / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f.name
        n = 1
        while target.exists():
            target = target_dir / f"{f.stem}_{n}{f.suffix}"
            n += 1
        if not args.dry_run:
            op(str(f), str(target))
        _line(i, len(files), r)
    with (dest / "classification.jsonl").open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    _summary(results)
    return 0


def cmd_evaluate(args) -> int:
    from .evaluate import evaluate

    clf = _make(args)
    if args.backend in ("ml", "hybrid"):
        print("note: evaluate on PDFs the model was NOT trained on, or the accuracy is meaningless; "
              "`pdfclf train` reports a cross-validated accuracy instead", file=sys.stderr)
    s = evaluate(clf, Path(args.labelled_dir), Path(args.report_dir), progress=_line)
    print(f"\naccuracy {s['accuracy']:.1%} on {s['samples']} PDFs  ·  ECE {s['ece']:.3f}", file=sys.stderr)
    print(f"report: {Path(args.report_dir) / 'report.md'}", file=sys.stderr)
    return 0


def cmd_train(args) -> int:
    """Train the paperless-ngx-style classifier (ml.py) for the primary question."""
    from collections import Counter

    from .classifier import file_identity
    from .evaluate import collect_samples
    from .extract import extract_text, head
    from .ml import TextCache, data_hash, load_model, train

    cfg = load_config(args.config)
    if not args.labelled_dirs and not args.from_db:
        print("give at least one labelled folder (<dir>/<label>/*.pdf) or --from-db", file=sys.stderr)
        return 2
    model_path = Path(args.model or cfg.ml_model_path)
    cache = TextCache(model_path.parent / "text-cache.jsonl")
    docs: dict[str, tuple[str, str]] = {}  # sha256 -> (label, text); later sources win
    skipped: Counter = Counter()

    for d in args.labelled_dirs:
        samples = collect_samples(Path(d))
        for i, s in enumerate(samples, 1):
            sha, _ = file_identity(s.path)
            key = f"{sha}:{cfg.max_pages}:{cfg.max_chars}:{cfg.ocr}:{cfg.ocr_language}"
            text = cache.get(key)
            if text is None:
                text = extract_text(s.path, max_pages=cfg.max_pages, ocr=cfg.ocr,
                                    ocr_language=cfg.ocr_language).head(cfg.max_pages, cfg.max_chars)
                cache.put(key, text)
            print(f"[{i:>4}/{len(samples)}] {s.truth:<16} {s.path.name}", file=sys.stderr)
            if len(text.strip()) < 50:
                skipped["too little text"] += 1
                continue
            docs[sha] = (s.truth, text)

    if args.from_db:
        from .db import connect, iter_training_docs

        n = 0
        with connect(cfg) as conn:
            for doc_id, label, text in iter_training_docs(conn, cfg, args.include_auto):
                docs[doc_id] = (label, head(text, cfg.max_pages, cfg.max_chars))
                n += 1
        print(f"{n} documents from PostgreSQL", file=sys.stderr)

    known = set(cfg.labels())
    for label, _ in docs.values():
        if label not in known:
            skipped[f"label '{label}' not in config"] += 1
    pairs = [(t, y) for y, t in docs.values() if y in known]
    for reason, n in skipped.items():
        print(f"skipped {n}: {reason}", file=sys.stderr)
    texts, labels = [t for t, _ in pairs], [y for _, y in pairs]

    if model_path.exists() and not args.force:
        try:
            if load_model(model_path).data_hash == data_hash(texts, labels):
                print(f"training data unchanged, keeping {model_path} (use --force to retrain)", file=sys.stderr)
                return 0
        except Exception as exc:  # unreadable/old model: just retrain
            print(f"replacing {model_path}: {exc}", file=sys.stderr)
    try:
        model = train(texts, labels, cfg.primary, min_df=cfg.ml_min_df, cv=not args.no_cv)
    except ValueError as exc:
        print(f"cannot train: {exc}", file=sys.stderr)
        return 1
    model.save(model_path)

    print(f"\ntrained on {model.n_samples} documents -> {model_path}", file=sys.stderr)
    for label, n in model.counts.items():
        print(f"  {label:<20} {n}", file=sys.stderr)
    missing = sorted(known - set(model.counts))
    if missing:
        print(f"  no examples (never predicted by the model): {', '.join(missing)}", file=sys.stderr)
    if model.cv_accuracy is not None:
        print(f"cross-validated accuracy: {model.cv_accuracy:.1%} ({model.cv_folds}-fold)", file=sys.stderr)
    elif not args.no_cv:
        print("cross-validation skipped: every label needs at least 2 examples", file=sys.stderr)
    return 0


def cmd_db_schema(args) -> int:
    from .db import build_schema

    print(build_schema(load_config(args.config)), end="")
    return 0


def cmd_db_setup(args) -> int:
    from .db import connect, ensure_schema

    cfg = load_config(args.config)
    with connect(cfg) as conn:
        what = ensure_schema(conn, cfg)
    print(f"table '{cfg.db_table}' {what}", file=sys.stderr)
    return 0


def _report_bulk(stats: dict) -> int:
    print(f"stored {stats['indexed']} documents, {len(stats['errors'])} errors", file=sys.stderr)
    for err in stats["errors"][:5]:
        print("  " + json.dumps(err, ensure_ascii=False)[:400], file=sys.stderr)
    return 1 if stats["errors"] else 0


def cmd_index(args) -> int:
    """Classify PDFs and write the results straight into PostgreSQL."""
    from .db import bulk_index, connect, ensure_schema

    clf = _make(args)
    files = _pdfs(args.paths, args.recursive)
    seen: list[Result] = []

    def gen():
        for i, f in enumerate(files, 1):
            r = clf.classify_file(f)
            _line(i, len(files), r)
            seen.append(r)
            yield r

    with connect(clf.cfg) as conn:
        ensure_schema(conn, clf.cfg)
        rc = _report_bulk(bulk_index(conn, clf.cfg, gen()))
    _summary(seen)
    return rc


def cmd_db_load(args) -> int:
    """Load an existing results .jsonl (from `classify -o x.jsonl --with-text`)."""
    from .db import bulk_index, connect, ensure_schema, read_jsonl

    cfg = load_config(args.config)
    with connect(cfg) as conn:
        ensure_schema(conn, cfg)
        return _report_bulk(bulk_index(conn, cfg, read_jsonl(args.jsonl)))


def cmd_review(args) -> int:
    from .db import connect, set_review

    cfg = load_config(args.config)
    if args.label not in cfg.labels():
        print(f"unknown label '{args.label}', expected one of {cfg.labels()}", file=sys.stderr)
        return 2
    try:
        with connect(cfg) as conn:
            set_review(conn, cfg, args.doc_id, args.label, args.by, args.note)
    except KeyError:
        print(f"no document with doc_id {args.doc_id}", file=sys.stderr)
        return 1
    print(f"review stored for {args.doc_id}", file=sys.stderr)
    return 0


def cmd_search(args) -> int:
    from .db import connect, search

    cfg = load_config(args.config)
    with connect(cfg) as conn:
        hits = search(conn, cfg, args.query, args.label, args.limit)
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0
    for h in hits:
        print(f"{h['rank']:.3f}  {str(h['label']):<16} {h['file']}  [{h['doc_id'][:12]}]")
        print("       " + " ".join(h["excerpt"].split()))
    print(f"{len(hits)} hits", file=sys.stderr)
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(args.config, args.backend), host=args.host, port=args.port)
    return 0


def _summary(results: list[Result]) -> None:
    from collections import Counter

    st = Counter(r.status for r in results)
    lab = Counter(r.label for r in results if r.status == STATUS_AUTO)
    print(f"\n{len(results)} PDFs: " + ", ".join(f"{k}={v}" for k, v in st.items()), file=sys.stderr)
    if lab:
        print("auto labels: " + ", ".join(f"{k}={v}" for k, v in lab.most_common()), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdfclf", description="Classify PDFs with Laya and/or a trained classifier.")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--backend", choices=BACKENDS, default="laya",
                    help="laya = zero-shot; ml = trained model (`pdfclf train`); hybrid = Laya + trained "
                         "model for the primary label; keyword = model-free stand-in for testing")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("classify", help="classify PDFs and print/write results")
    p.add_argument("paths", nargs="+")
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("-o", "--out", help="results file (.jsonl or .csv)")
    p.add_argument("--with-text", action="store_true", help="include extracted text in .jsonl output")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("index", help="classify PDFs and store the results in PostgreSQL")
    p.add_argument("paths", nargs="+")
    p.add_argument("-r", "--recursive", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("db-load", help="load a results .jsonl into PostgreSQL")
    p.add_argument("jsonl")
    p.set_defaults(func=cmd_db_load)

    p = sub.add_parser("db-setup", help="create the table and its indexes if missing")
    p.set_defaults(func=cmd_db_setup)

    p = sub.add_parser("db-schema", help="print the SQL schema generated from the config")
    p.set_defaults(func=cmd_db_schema)

    p = sub.add_parser("search", help="full-text search over stored documents")
    p.add_argument("query", help='web-search syntax: words, "phrases", -exclude, or')
    p.add_argument("-l", "--label", action="append", help="only this label (repeatable)")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("review", help="record the correct label for a document (human feedback)")
    p.add_argument("doc_id", help="the document's sha256 (doc_id)")
    p.add_argument("label")
    p.add_argument("--by", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("sort", help="copy (or move) PDFs into <dest>/<label>/, low confidence into _review/")
    p.add_argument("source")
    p.add_argument("dest")
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("--move", action="store_true", help="move instead of copy")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sort)

    p = sub.add_parser("evaluate", help="measure accuracy on <dir>/<label>/*.pdf")
    p.add_argument("labelled_dir")
    p.add_argument("--report-dir", default="eval-report")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("train", help="train the paperless-ngx-style classifier for the primary question")
    p.add_argument("labelled_dirs", nargs="*", help="folders laid out as <dir>/<label>/*.pdf")
    p.add_argument("--from-db", action="store_true", help="also learn from reviewed documents in PostgreSQL")
    p.add_argument("--include-auto", action="store_true",
                   help="with --from-db: also learn from unreviewed 'auto' results (can reinforce mistakes)")
    p.add_argument("--model", help="output path (default: ml.model_path from the config)")
    p.add_argument("--force", action="store_true", help="retrain even if the training data is unchanged")
    p.add_argument("--no-cv", action="store_true", help="skip cross-validation")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("serve", help="run the HTTP API")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
