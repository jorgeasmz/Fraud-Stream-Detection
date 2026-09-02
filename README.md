# Fraud Stream Detection

Scores card transactions and ranks them for a review team that can work a fixed
number of alerts a day. Over an 85-day held-out period, 62 of every 100 alerts are
fraudulent, against 0.7 for the same queue in arbitrary order.

![CI](https://github.com/jorgeasmz/Fraud-Stream-Detection/actions/workflows/ci.yml/badge.svg)

## Corpus

The transactions come from the simulator published with the Fraud Detection
Handbook (Le Borgne and Bontempi, Université Libre de Bruxelles), one file per
simulated day, downloaded without authentication.

| | |
|---|---:|
| Transactions | 1,754,155 |
| Frauds | 14,681 |
| Fraud rate | 0.837% |
| Period | 2018-04-01 to 2018-09-30 |
| Customers | 4,990 |
| Terminals | 10,000 |

A simulator is used rather than a public fraud dataset because the two public ones
carry no entity identifier. The features this system exists to compute are
windowed per card and per terminal, and a table of anonymised principal components
cannot express them.

Every fraud carries the scenario that produced it, and the three differ in what
makes them visible.

| Scenario | Frauds | Signature |
|---|---:|---|
| 1 | 973 | Every amount above 220, and no legitimate transaction reaches it |
| 2 | 9,077 | 357 terminals compromised for a median of 26 days, at amounts averaging 53.81 against 52.98 for legitimate traffic |
| 3 | 4,631 | 487 cards compromised for a median of 11 days, at amounts averaging 260.92 |

Scenario 2 is 62% of all frauds and its transactions are indistinguishable from
legitimate ones by amount. That is what places a ceiling on any detector fitted
without labels, and reporting recall per scenario rather than one aggregate is
what makes the ceiling visible.

## Features

Eighteen features per transaction: the amount, the hour, a weekend flag, and
rolling counts and mean amounts per customer and per terminal over 1, 7 and 30
days, plus the ratio of the amount to the customer's window mean.

Every window is prior-only. A scorer running on an arriving transaction has not
seen that transaction, so including it in its own window would report a quality
the live path cannot reach.

The ratio is regularised by one currency unit. Forty-two transactions carry an
amount of zero, and a customer whose window contains only those produces an
unbounded ratio under a plain division, which reached 7.65e7 and a standard
deviation of 72,144 across the table.

Features derived from past labels live in a separate module. A label arrives when
a dispute resolves, not when the transaction happens, so every risk window ends
seven days before the transaction it describes, expressed as the difference of two
windows that end now. The evaluation refuses to run a detector that declares
itself label-free while reading one of those columns.

## Evaluation protocol

The detector is fitted on 2018-04-01 to 2018-06-30 and scored on 2018-07-08 to
2018-09-30. The week between them is the delay a label takes to come back.

| | Rows |
|---|---:|
| Training period | 872,795 |
| Held-out period | 813,843 |

Accuracy is meaningless at 0.837% positives, and so is a global threshold. A team
works a fixed number of alerts a day, so the metric is precision at that depth,
measured per day and averaged.

Card precision is reported alongside it because a team investigates cards, not
transactions. Three alerts on one compromised card are one investigation, and
transaction precision counts them as three hits.

## Detector comparison

| Detector | Labels | Card p@100 | p@20 | p@50 | p@100 | p@200 | Recall s1 | Recall s2 | Recall s3 |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `random` | | 0.026 | 0.008 | 0.007 | 0.007 | 0.008 | 0.009 | 0.009 | 0.008 |
| `amount` | | 0.183 | 0.863 | 0.397 | 0.209 | 0.112 | **1.000** | 0.011 | 0.576 |
| `deviation` | | 0.219 | 0.898 | 0.479 | 0.266 | 0.141 | 0.909 | 0.007 | 0.815 |
| `isolation_forest`, 18 features | | 0.186 | 0.631 | 0.354 | 0.212 | 0.124 | 0.417 | 0.007 | 0.707 |
| `isolation_forest`, 4 features | | 0.218 | 0.671 | 0.428 | 0.265 | 0.142 | 0.998 | 0.008 | 0.791 |
| `supervised`, label-free features | ✓ | 0.226 | 0.946 | 0.540 | 0.286 | 0.148 | 0.982 | 0.007 | 0.878 |
| **`supervised`, with delayed risk** | ✓ | **0.561** | **0.972** | **0.900** | **0.620** | **0.329** | 0.916 | **0.664** | 0.819 |

`amount` ranks by the amount alone, which is the rule a fraud team writes first.
It recovers scenario 1 completely, since the simulator places every scenario-1
fraud above a threshold no legitimate transaction reaches.

The isolation forest over all eighteen features scores below ranking by a single
one. Restricting it to the amount and the three deviation ratios raises p@100 from
0.212 to 0.265 and scenario-1 recall from 0.417 to 0.998. An isolation score
measures rarity across every dimension it is given, and terminal activity and hour
of day are rare in ways unrelated to fraud, so each uninformative dimension
dilutes the signal. Dropping the six terminal features alone recovers 0.254.

No label-free detector exceeds 0.011 recall on scenario 2, which is chance at this
budget. Delayed labels are the only thing that sees it: the terminal risk of a
scenario-2 fraud averages 0.612 against 0.005 for legitimate traffic, and adding
the twelve risk columns takes scenario-2 recall to 0.664 and p@100 from 0.286 to
0.620.

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python -m ingest.prepare        # downloads 183 days and builds the table
python -m evaluation.offline    # fits every detector and prints the comparison
```

Ingestion takes about 20 seconds and caches the day files, so a repeated run
downloads nothing. The comparison takes about 70 seconds, most of it the two
isolation forests scoring 813,843 rows.

## Development

```bash
pip install -r requirements-dev.txt

pytest              # 28 tests
ruff check .
```

No test reaches the network or reads the corpus. The window tests assert the
prior-only property on hand-built frames of two transactions, where the expected
value is arithmetic rather than a recorded output.

## Project structure

```text
Fraud-Stream-Detection/
├── ingest/
│   ├── config.py         # Source, cache paths and the period split
│   ├── download.py       # Day files, cached and resumable
│   └── prepare.py        # Day files to one time-ordered table
├── features/
│   ├── config.py         # The feature contract shared by every path
│   ├── offline.py        # Label-free windows, computed in batch
│   └── risk.py           # Windows over past labels, ending before the delay
├── detect/
│   ├── config.py         # Model settings
│   └── detectors.py      # Baselines, isolation forest and the supervised model
├── evaluation/
│   ├── config.py         # Review budget
│   ├── metrics.py        # Precision at k, card precision, recall per scenario
│   └── offline.py        # The comparison, with the label-free guard
└── tests/                # pytest suite, offline
```
