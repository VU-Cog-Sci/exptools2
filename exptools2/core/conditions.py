from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class ConditionsLoader:
    @staticmethod
    def load(path: str | Path, key: str | None = None) -> list[dict[str, Any]]:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".tsv":
            return ConditionsLoader.load_tsv(path)
        if suffix in {".h5", ".hdf5"}:
            return ConditionsLoader.load_hdf5(path, key=key)
        raise ValueError(f"Unsupported conditions format: {path}")

    @staticmethod
    def load_tsv(path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        with path.open("r", encoding="utf8", newline="") as f_in:
            reader = csv.DictReader(f_in, delimiter="\t")
            return [dict(row) for row in reader]

    @staticmethod
    def load_hdf5(path: str | Path, key: str | None = None) -> list[dict[str, Any]]:
        path = Path(path)

        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pandas is required for HDF5 conditions") from exc

        hdf_key = key or "conditions"
        df = pd.read_hdf(path, key=hdf_key)
        return df.to_dict(orient="records")
