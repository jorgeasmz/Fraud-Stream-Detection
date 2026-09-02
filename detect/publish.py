"""Publishes the fitted detector as a model repository, with a card built from the run.

The metrics in the card are read from the artifact the training wrote rather than
typed in, so the documented numbers and the recorded run cannot drift apart.

Usage: python -m detect.publish [--repo jorgeasmz/fraud-stream-detector]
"""

from __future__ import annotations

import argparse
import json
import logging

from huggingface_hub import HfApi

from detect.config import DECISION_FILE, MODEL_FILE, MODEL_REPO
from detect.train import DECISION_PATH, MODEL_PATH
from features.config import WINDOWS
from features.risk import LABEL_DELAY_DAYS

log = logging.getLogger(__name__)

SCENARIOS = {
    "1": "an amount above a threshold no legitimate transaction reaches",
    "2": "a terminal compromised for about four weeks, at ordinary amounts",
    "3": "a card compromised for about two weeks, at multiplied amounts",
}

CARD = """---
license: apache-2.0
library_name: sklearn
pipeline_tag: tabular-classification
tags:
  - fraud-detection
  - streaming
  - tabular
---

# Fraud stream detector

Scores a card transaction as it arrives and ranks it for a review team that works a
fixed number of alerts a day. Fitted on {training_rows:,} transactions over
{training_days} days of the simulator published with the Fraud Detection Handbook
(Le Borgne and Bontempi, Université Libre de Bruxelles).

## Metrics

Measured on the following {held_out_days} days, {held_out_rows:,} transactions, at a
budget of {daily_budget} alerts a day.

| Metric | Value |
|---|---:|
| Precision at the budget | {precision_at_budget:.3f} |
| Card precision at the budget | {card_precision_at_budget:.3f} |
{scenario_rows}

Each fraud pattern is reachable through a different family of features, so recall
per pattern says which signal the detector is using rather than reporting one
aggregate.

Precision at the budget is measured per day and averaged. Card precision counts a
card once however many of its transactions were flagged, since a team investigates
cards rather than transactions.

Accuracy is not reported. At a fraud rate below one percent it is a measure of the
base rate, and a detector that flags nothing scores above 0.99 on it.

## Operating point

**{threshold:.6f}**, the score whose expected alert rate equals {daily_budget} alerts a
day at the training period's volume. A review team is a rate rather than a
probability, so the operating point is a quantile of the training scores and an
output of the fit rather than a constant in the serving code.

## Inputs

{feature_count} features per transaction, in the order recorded in `{decision_file}`:
the amount, the hour, a weekend flag, rolling counts and mean amounts per card and
per terminal over {windows} days, the ratio of the amount to the card's window mean,
and fraud rates per card and per terminal over the same windows.

Every window is prior-only: a scorer has not seen the transaction it is judging, so
including it in its own window would report a quality the live path cannot reach.

The fraud-rate features end {delay} days before the transaction they describe, which
is the delay a dispute takes to resolve. Without them the detector cannot reach the
compromised-terminal pattern at all: no configuration fitted without labels exceeds
chance on it, and with them its recall is {scenario_2:.3f}.

## Limitations

The corpus is simulated. Its three fraud patterns are documented and separable,
which is what makes recall per pattern meaningful, and it is not evidence of
behaviour on real card traffic.

The artifact is a pickle and executes on load. Load it only from a repository you
control.

Trained by [Fraud-Stream-Detection](https://github.com/jorgeasmz/Fraud-Stream-Detection).
"""


def build_card(decision: dict) -> str:
    rows = "\n".join(
        f"| Recall, {SCENARIOS.get(scenario, 'scenario ' + scenario)} | {value:.3f} |"
        for scenario, value in sorted(decision["scenario_recall"].items())
    )
    return CARD.format(
        scenario_rows=rows,
        feature_count=len(decision["columns"]),
        decision_file=DECISION_FILE,
        windows=", ".join(str(days) for days in WINDOWS),
        delay=LABEL_DELAY_DAYS,
        scenario_2=decision["scenario_recall"]["2"],
        **{key: decision[key] for key in decision if key not in {"columns", "scenario_recall"}},
    )


def publish(repo: str = MODEL_REPO, private: bool = False) -> str:
    decision = json.loads(DECISION_PATH.read_text())
    card = DECISION_PATH.parent / "README.md"
    card.write_text(build_card(decision))

    api = HfApi()
    api.create_repo(repo, repo_type="model", private=private, exist_ok=True)
    for path, name in ((MODEL_PATH, MODEL_FILE), (DECISION_PATH, DECISION_FILE),
                       (card, "README.md")):
        api.upload_file(path_or_fileobj=str(path), path_in_repo=name, repo_id=repo)

    url = f"https://huggingface.co/{repo}"
    log.info("published to %s", url)
    return url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=MODEL_REPO)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--card-only", action="store_true", help="write the card without uploading")
    args = parser.parse_args()

    if args.card_only:
        print(build_card(json.loads(DECISION_PATH.read_text())))
        return
    print(publish(args.repo, args.private))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
