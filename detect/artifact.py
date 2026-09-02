"""Locates the fitted detector and the operating point that goes with it."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from detect.config import ARTIFACT_DIR, DECISION_FILE, LOCAL_ARTIFACTS, MODEL_FILE, MODEL_REPO

log = logging.getLogger(__name__)


def resolve() -> tuple[Path, dict]:
    """A local directory wins, so an export can be served before it is published.

    The file is a pickle, which executes on load. The model repository is therefore
    the trust boundary, and `MODEL_REPO` should name one the deployment controls.
    """
    local = Path(LOCAL_ARTIFACTS) if LOCAL_ARTIFACTS else ARTIFACT_DIR
    if (local / MODEL_FILE).exists():
        source = local / MODEL_FILE
        decision = json.loads((local / DECISION_FILE).read_text())
        log.info("detector from %s", source)
        return source, decision

    from huggingface_hub import hf_hub_download

    source = Path(hf_hub_download(MODEL_REPO, MODEL_FILE))
    decision = json.loads(Path(hf_hub_download(MODEL_REPO, DECISION_FILE)).read_text())
    log.info("detector from %s", MODEL_REPO)
    return source, decision
