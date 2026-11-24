# Unfair-terms model

LegalLens ships a trained classifier that flags Terms of Service sentences resembling eight
categories of potentially unfair clauses. It is the classical baseline from the LegalLens research
notebook (Colab), rebuilt here and checked against the notebook's recorded results.

It runs on `POST /api/audit` only. The web pages, the compliance score and every other report field
are the same whether it runs or not.

## What it flags

| Category (`category`) | Threshold | Test precision | Test recall |
|---|---|---|---|
| Limitation of liability (`limitation_of_liability`) | 0.80 | 0.87 | 0.68 |
| Unilateral termination (`unilateral_termination`) | 0.60 | 0.61 | 0.79 |
| Unilateral change (`unilateral_change`) | 0.80 | 0.78 | 0.55 |
| Content removal (`content_removal`) | 0.70 | 0.48 | 0.77 |
| Contract by using (`contract_by_using`) | 0.75 | 0.84 | 0.70 |
| Choice of law (`choice_of_law`) | 0.65 | 0.86 | 0.92 |
| Jurisdiction (`jurisdiction`) | 0.60 | 0.86 | 0.75 |
| Arbitration (`arbitration`) | 0.70 | 0.83 | 0.71 |

Held-out test set (1,607 sentences): macro-F1 0.7386, micro-F1 0.7213, weighted-F1 0.7244,
exact-match accuracy 0.9471, macro average precision 0.8196. Each threshold was chosen on the
validation set, never on the test set.

## The model

- **Data:** LexGLUE `unfair_tos` (`coastalcph/lex_glue`), official splits: 5,532 train, 2,275
  validation, 1,607 test sentences.
- **Features:** word TF-IDF, 1–2 grams, `min_df=2`, sublinear term frequency, L2 norm, accents
  stripped. The vocabulary has 20,343 terms.
- **Classifier:** one-vs-rest logistic regression (liblinear, `class_weight="balanced"`, seed 42),
  with one threshold per category.
- **Files:** `legallens/compliance/unfair_tos/` holds about 650 KB:
  - `model.json`: labels, thresholds, intercepts, provenance, recorded metrics, and the sha256 of
    each data file.
  - `vocab.txt.gz`: the vocabulary, one term per line, in column order.
  - `weights.f32.gz`: the idf values followed by the 8 coefficient rows, as little-endian float32.

## How it runs

`legallens/compliance/unfair_terms.py` reproduces scikit-learn's predictions in plain Python, so the
app needs no numpy, scikit-learn or pickle files and `requirements.txt` is unchanged. On all 1,607
test sentences its probabilities match scikit-learn's to within 4.3e-8, with no threshold decision
different. `tests/fixtures/unfair_tos_parity.json` keeps a 40-sentence check in the test suite.

For each clause, the engine splits the clause text into sentences (headings are never classified)
and scores every sentence. A clause gets a category when its best sentence reaches that category's
threshold, and that sentence is the evidence. The model loads on the first `/api/audit` request
(about 7 ms) and checks the sample Terms of Service in about 4 ms.

The model files are checked against their sha256 when they load. If they are missing or corrupt,
or the model fails for any other reason, the audit still succeeds and `status` says `unavailable`.

## API

`POST /api/audit` adds one key. This is the response for `data/samples/sample_tos.txt`, first of its
six flags shown:

```json
"unfair_terms": {
  "status": "ok",
  "model": {"name": "tfidf-logreg-unfair-tos", "format_version": 1,
            "dataset": "LexGLUE UNFAIR-ToS", "test_macro_f1": 0.7386},
  "note": "Indicators of resemblance to UNFAIR-ToS benchmark categories, not legal conclusions. A clause with no flag is not thereby fair. Not part of the compliance score.",
  "sentences_checked": 15,
  "flags": [
    {"id": "u1", "clause_index": 4, "category": "unilateral_change", "label": "Unilateral change",
     "score": 0.9988, "threshold": 0.8,
     "evidence": {"start": 611, "end": 646, "text": "We may change our fees at any time."},
     "suggestion": "Provide advance notice of material changes, explain their impact on users and consider allowing users to discontinue the service where appropriate."}
  ]
}
```

Flags are ordered by clause, then by score. One sentence can carry more than one category: the same
fee sentence is also flagged as unilateral termination (0.79), which is a weaker and less obvious
match.

- `status` is `ok`, `disabled` (switched off) or `unavailable` (the model could not run). When it is
  not `ok`, `model` is `null`, `flags` is empty and `sentences_checked` is 0.
- `score` is the model's output for the evidence sentence. It is not a probability that the clause
  is legally unfair.
- `evidence` is `null` when the sentence can't be located in the document text.
- The `POST /audit` results page and its JSON export do not include this key.

To switch the model off, set `LEGALLENS_UNFAIR_MODEL=off` (or `0`, `false`, `no`).

## Limits

- The categories come from a research benchmark of English-language consumer Terms of Service,
  not from Indian law. A flag means the wording resembles a benchmark category, not that the
  clause breaks a rule.
- A clause with no flag is not shown to be fair. Recall ranges from 0.55 (unilateral change) to 0.92
  (choice of law), so some clauses of every category will be missed.
- Sentence splitting is a heuristic and has not been validated on its own.
- The model reads only the words. It can't tell "we may sell your data" from "we never sell your
  data".

## Rebuilding

The build script trains the model again, stops if any recorded value differs, then exports the files
and checks the engine against scikit-learn:

```powershell
py -3.13 -m venv $env:TEMP\model-venv
& $env:TEMP\model-venv\Scripts\python.exe -m pip install -r scripts/requirements-model.txt
& $env:TEMP\model-venv\Scripts\python.exe scripts/build_unfair_model.py
```

It prints `REPRODUCE: PASS` and `PARITY: PASS`. Two runs write byte-identical files. The pinned
versions (scikit-learn 1.6.1, numpy 2.4.6, scipy 1.16.3) match the notebook's environment, and the
web app never installs them.
