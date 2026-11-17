# laya-pdf-classifier

Prototype for classifying PDFs with [Laya](https://huggingface.co/convaiinnovations/laya), a
non-generative decision model that returns typed answers with confidence scores, and with a
classifier trained on your own documents, the way [paperless-ngx](https://docs.paperless-ngx.com/advanced_usage/#automatic-matching) does it.

```
                                      ┌─► Laya (zero-shot): all questions ──────────┐
PDF ──► text (Docling, OCR fallback) ─┤                                             ├─► label + confidence
                                      └─► trained model (n-grams → MLP): primary ───┘     ├─ ≥ threshold → auto
                                                                                          └─ < threshold → review
```

You define the categories in `config.yaml`; no training is needed to get started. Once you have
labelled or reviewed some documents, `pdfclf train` learns from them (see [Trained classifier](#trained-classifier-paperless-ngx-style)). The same
pipeline is available as a CLI (classify, sort into folders, evaluate) and as an HTTP API.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # or the CUDA build
pip install -e ".[dev]"
cp config.example.yaml config.yaml

# smoke test without downloading the model (keyword stand-in, not a real classifier)
python tools/make_samples.py samples
pdfclf --backend keyword classify samples -r

# the real thing (first run downloads ~1 GB of weights from Hugging Face)
pdfclf classify ~/Documents/scans -r -o results.csv
pdfclf sort ~/Documents/inbox ~/Documents/sorted -r        # copies into sorted/<label>/ and sorted/_review/
pdfclf serve --port 8080                                   # HTTP API
pdfclf index ~/Documents/scans -r                          # classify + store in PostgreSQL
pdfclf search "Kündigung Mietvertrag"                      # full-text search over stored documents

# learn from your own documents (labelled/<label>/*.pdf), then use the trained model
pdfclf train labelled/
pdfclf --backend hybrid classify ~/Documents/inbox -r
```

With Docker:

```bash
cp config.example.yaml config.yaml
docker compose up --build
curl -F file=@rechnung.pdf http://localhost:8080/classify
```

## Configuration

`config.yaml` holds everything you are likely to change:

| Key | Meaning |
|---|---|
| `model.checkpoint` | `multilingual` (default, 100+ languages, 1024 tokens), `english` (512 tokens), `typed-decisions`, or `auto` (Router decides per document) |
| `model.scan` | `first` scores the first token window only; `long` slides over all extracted text and aggregates |
| `model.max_len` / `head_max_len` | Optional token-budget overrides |
| `extraction.max_pages` / `max_chars` | How much of each PDF goes to the model |
| `extraction.index_max_pages` | How many pages are extracted, stored and searchable (empty = all) |
| `extraction.ocr` / `ocr_language` | OCR scanned PDFs with Docling (Tesseract if installed, else Docling's default engine) |
| `decision.primary` | The choice question that is "the" class (used for sorting and evaluation) |
| `decision.min_confidence` | Below this, results get status `review` (per-question override: `min_confidence` on the question) |
| `questions` | `choice` (labels → description), `noul` (yes/no probability), `score` (ordered levels) |
| `ml.model_path` | Where `pdfclf train` writes the trained classifier |
| `ml.combine` / `weight` | `--backend hybrid`: `ml` (trained model decides the primary label) or `average` (`weight` × model + (1 − `weight`) × Laya) |
| `ml.min_df` | Ignore words/bigrams found in fewer than this share of training documents |

The description next to each label is what Laya compares the text against, so it matters most.
Keep descriptions short and distinctive, and include the words that actually appear in your documents
(e.g. both "invoice" and "Rechnung"). With more than 16 labels the classifier automatically switches to
Laya's `predict_tournament` (labels are judged in groups, then the finalists).

## Measuring accuracy: do this first

Laya's base checkpoints are weak zero-shot and over-confident, so measure before you trust it:

1. Put 10–30 real PDFs per label into `labelled/<label>/` (folder names = label keys in the config).
2. Run `pdfclf evaluate labelled/ --report-dir eval-report`.
3. Read `eval-report/report.md`:
   - **accuracy** and the **confusion matrix** show which labels get mixed up. Sharpen those descriptions, merge labels, or split the question.
   - **accuracy vs. coverage** shows what `min_confidence` buys you: at 0.8, maybe 60% of PDFs are handled automatically at 95% accuracy.
   - **ECE** (expected calibration error) shows how far confidence is from reality.
4. `eval-report/predictions.jsonl` has every answer, including all class probabilities.

Iterate on the descriptions until the numbers stop improving. If they plateau too low, fine-tune.

## Trained classifier (paperless-ngx style)

paperless-ngx does not understand documents; it learns from the ones you have already filed.
Each document's text is lowercased, stripped of punctuation, and turned into word and word-pair
counts (scikit-learn `CountVectorizer`, 1–2 grams). A small neural network (`MLPClassifier`) is
trained on those counts and retrained when the filed documents change. `pdfclf/ml.py` does the
same for the primary question. One small change: numbers are dropped, because invoice numbers,
amounts and dates differ in every document.

| | Laya (`--backend laya`) | Trained (`--backend ml`) | Hybrid (`--backend hybrid`) |
|---|---|---|---|
| Needs training data | no | yes, ideally 10+ per label | no; uses the model once it exists |
| Learns your senders/layouts | no | yes | yes |
| Yes/no and score questions | yes | no | yes (Laya) |
| Inference cost | transformer forward pass | milliseconds on CPU | about Laya's |
| Dependencies | torch, ~1 GB weights | scikit-learn | both |

**Training data** comes from labelled folders, from human reviews in PostgreSQL, or from both:

```bash
pdfclf train labelled/                          # labelled/<label>/*.pdf, folder names = label keys
pdfclf train --from-db                          # documents with a `pdfclf review` label
pdfclf train labelled/ --from-db --include-auto # also confident unreviewed results (can reinforce mistakes)
```

`train` prints how many examples each label has, which labels have none (the model can never
predict them), and a **cross-validated accuracy**: an honest estimate, because each document is
scored by a model that did not see it during training. Don't run `pdfclf evaluate` with
`--backend ml` on the training folder; the model has memorised it. Extracted text is cached in
`models/text-cache.jsonl`, so retraining doesn't re-run Docling. If the training data hasn't
changed, `train` does nothing (`--force` retrains anyway), so it is cheap to run from cron, the way
paperless-ngx retrains hourly. The model file is re-read when it changes, so a running server picks
up the new model without a restart.

**The workflow:**

1. Start with `--backend laya` (zero-shot). Store results in PostgreSQL (`pdfclf index`).
2. Correct wrong labels with `pdfclf review <doc_id> <label>`.
3. `pdfclf train --from-db` (plus any labelled folders) as soon as each label has a few examples.
4. Switch to `--backend hybrid`: the trained model sets the label, Laya keeps answering the yes/no and
   score questions. With `ml.combine: average` both vote, which helps while training data is thin.
   The primary answer keeps both opinions under `answers.<primary>.sources`.
5. Keep reviewing and retraining. Every correction improves the model.

The model file is a Python pickle: only load files you trained yourself, and retrain after
upgrading scikit-learn (you'll get a warning).

## HTTP API

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | | backend name |
| GET | `/labels` | | configured labels and questions |
| GET | `/model` | | trained classifier: labels, sample counts, CV accuracy (or `null`) |
| POST | `/classify` | multipart `file` (PDF) | result JSON |
| POST | `/classify-text` | `{"text": "..."}` | result JSON |

Result (shortened):

```json
{
  "file": "rechnung.pdf",
  "label": "invoice",
  "confidence": 0.91,
  "status": "auto",
  "flags": {"needs_payment": 0.87, "contains_personal_data": 0.12, "urgency": 1.4},
  "low_confidence": [],
  "answers": {"document_type": {"choice": "invoice", "probabilities": {"invoice": 0.91, "...": 0.0}, "confidence": 0.91}},
  "warnings": [], "ocr_used": false, "model": "multilingual", "elapsed_ms": 140
}
```

## PostgreSQL

Results are stored as one row per PDF in the `database.table` table, keyed by the file's SHA-256, so
re-classifying a file updates its row. A row holds file metadata, the extracted text, the primary
label and status as columns, every answer with its confidence in an `answers` jsonb column, and an
optional human review (`review_label`, `reviewed_by`, `reviewed_at`, `review_note`). Re-classifying
keeps the review. Adding questions or labels needs no migration.

```bash
docker compose -f docker-compose.yml -f docker-compose.db.yml up -d postgres   # local dev database
pdfclf db-schema                       # print the CREATE TABLE generated from the config
pdfclf db-setup                        # create it (index/db-load/the API also do this on first use)
pdfclf index ~/Documents/scans -r      # classify + store
pdfclf db-load results.jsonl           # store the output of `classify -o results.jsonl --with-text`
pdfclf review <doc_id> <label> --by me # record the correct label
pdfclf search "Rechnung Stadtwerke" -l invoice   # websearch syntax: "phrase", -exclude, or
```

The API takes `POST /classify?store_result=true`. The connection comes from `database.url`, or
`DATABASE_URL` if it is set. Full-text search stems German and English words (`database.text_search`).
Plain SQL works too:

```sql
-- low-confidence results still waiting for a human
SELECT doc_id, file_name, label, confidence FROM documents
WHERE status = 'review' AND review_label IS NULL ORDER BY confidence;

-- where the model and the reviewers disagree
SELECT label, review_label, count(*) FROM documents
WHERE review_label IS NOT NULL AND review_label IS DISTINCT FROM label GROUP BY 1, 2 ORDER BY 3 DESC;

-- documents that ask for payment
SELECT file_name FROM documents WHERE (answers -> 'needs_payment' ->> 'value')::boolean;
```

## Next steps

- **Calibration:** Laya ships `laya.fit_temperatures` / `fit_abstention_thresholds`. Feed them the probabilities from `predictions.jsonl` to get honest confidences.
- **More than one learned field:** paperless-ngx also learns correspondents, tags and storage paths. `ml.py` trains one model for `decision.primary`; more choice questions would follow the same pattern with one model file each.
- **Fine-tuning:** the Laya repo has a [Kaggle notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb) (free 2×T4). Your labelled folders are the dataset. Point `model.checkpoint` at the result by extending `LayaBackend` with `Router(models=...)`.
- **paperless-ngx:** add a workflow (trigger *Document Added*, action *Webhook*) that calls a small adapter. The adapter fetches `/api/documents/{id}/` (content), calls `/classify-text`, and `PATCH`es `document_type` when `status == "auto"`.

## Layout

```
pdfclf/extract.py     PDF → text via Docling, OCR fallback
pdfclf/config.py      YAML → Laya question schema, validation
pdfclf/backends.py    LayaBackend (Router / predict_long / predict_tournament), HybridBackend, KeywordBackend stand-in
pdfclf/ml.py          trained classifier (paperless-ngx style): preprocessing, training, CV, MLBackend
pdfclf/classifier.py  pipeline + confidence gating
pdfclf/evaluate.py    accuracy, per-class metrics, confusion matrix, ECE, threshold sweep
pdfclf/server.py      FastAPI
pdfclf/db.py          PostgreSQL: schema, result → row, upserts, reviews, full-text search
pdfclf/cli.py         classify | sort | evaluate | train | serve | index | search | db-load | db-setup | db-schema | review
tools/make_samples.py synthetic sample PDFs for smoke tests
tests/                pytest (runs without torch or Laya weights; set PDFCLF_TEST_DATABASE_URL for the PostgreSQL tests)
```
