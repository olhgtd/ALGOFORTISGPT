"""Exact approved-file loading for backtests; no global or sample feed fallback."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pandas as pd


class DatasetUnavailable(ValueError):
    pass


class ApprovedDatasetFiles:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def fetch_dataset(self, dataset):
        logical = Path(dataset["logicalPath"])
        path = (self.root / logical).resolve()
        if logical.is_absolute() or not path.is_relative_to(self.root):
            raise DatasetUnavailable("DATASET_PATH_OUTSIDE_ROOT")
        try:
            payload = path.read_bytes()
        except OSError:
            raise DatasetUnavailable("DATASET_FILE_MISSING") from None
        digest = sha256(payload).hexdigest()
        if digest != dataset["hashSha256"].removeprefix("sha256:"):
            raise DatasetUnavailable("DATASET_HASH_MISMATCH")
        try:
            # Hash and decode the SAME bytes, even if the source is replaced.
            frame = pd.read_parquet(BytesIO(payload))
        except Exception:
            raise DatasetUnavailable("DATASET_FORMAT_INVALID") from None
        return frame, digest
