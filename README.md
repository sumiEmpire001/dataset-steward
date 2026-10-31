# Dataset Steward

Deterministic CSV profiling, exact duplicate detection, quality rules and reviewable, reversible cleaning. Python 3.10+, standard library only. No model or external data service is used.

```sh
python -m unittest discover -s tests -v
python demo.py
```

```python
from steward import Dataset
source = Dataset.from_csv('name,age\n Ada ,12\nAda,12\nBo,\n')
print(source.profile())
print(source.check({'age': {'required': True, 'type': 'integer', 'min': 0}}))
proposal = source.propose(trim=['name'], missing={'age': 'unknown'}, drop_duplicates=True)
# Inspect proposal['changes'] and proposal['removed_rows'] before applying.
cleaned = source.apply(proposal)
assert cleaned.undo(proposal).snapshot() == source.snapshot()
print(cleaned.to_csv())
```

Profiles report whitespace, missing cells, exact distinct counts, type compatibility and exact duplicate row groups. Key-based duplicate grouping is available via `duplicates(['column'])`. Row indices are zero-based data-row indices, excluding the header. Headers and duplicate matches are exact; no fuzzy merge or inferred entity resolution.

Quality rules: required, unique, text/integer/decimal/date, string enum and numeric min/max. Validation trims values for comparisons, without changing the dataset. Empty/whitespace cells count as missing; uniqueness ignores missing values. Dates require ISO YYYY-MM-DD. Integers use optional single sign and ASCII digits. Decimal rules use Python Decimal parsing, reject nonfinite values, and avoid floating-point arithmetic.

Cleaning proposals support explicit column trimming, missing-value replacement and exact duplicate removal after transformations. They include explanations, original/cleaned snapshots and fingerprints. `apply` regenerates and compares the entire proposal; altered plans and stale datasets fail. `undo` verifies the output fingerprint and regenerates the plan before restoring every original value and row. APIs return new datasets rather than mutating the source; original files are never overwritten.

CSV round trips preserve cell content, including quotes, non-ASCII and multiline fields, while normalising line endings/quoting and removing an initial BOM. Byte-for-byte source-file restoration is not claimed. Raw CSV is lossless at cell level. `to_csv(spreadsheet_safe=True)` prefixes formula-like cells and headers for spreadsheet viewing; that intentionally changes those strings and should not be used for exact round trips.

12 tests cover known dirty fixtures, deterministic proposals, schema rules, duplicates, numeric/date edges, invalid shapes, stale/tampered plans, exact undo, CSV round trips, spreadsheet-safe output and defensive copies. GitHub Actions runs tests and the synthetic demo on Python 3.10/3.12/3.13; Actions → Tests and demo → Run workflow repeats them.

Limits: in-memory local engine, up to 100 columns/10000 rows, 8 MiB aggregate cell bytes and 10 MiB CSV input. No streaming, authentication, encryption, automatic disk persistence or machine-learning anomaly model. Review plans contain original data; treat them with the same privacy controls as the source. Hashes detect accidental mismatch, not malicious replacement of a dataset and all its evidence. Cleaning rules reflect explicit choices, not a guarantee that a dataset is correct.
