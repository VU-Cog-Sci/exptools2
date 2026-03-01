from __future__ import annotations

import re
from pathlib import Path

BIDS_STEM_RE = re.compile(
    r"^sub-(?P<sub>[A-Za-z0-9]+)_ses-(?P<ses>[A-Za-z0-9]+)_task-(?P<task>[A-Za-z0-9]+)_run-(?P<run>[A-Za-z0-9]+)$"
)


class BidsStemError(ValueError):
    pass


def make_bids_stem(sub: str, ses: str, task: str, run: str | int) -> str:
    stem = f"sub-{sub}_ses-{ses}_task-{task}_run-{run}"
    parse_bids_stem(stem)
    return stem


def parse_bids_stem(stem: str) -> dict[str, str]:
    match = BIDS_STEM_RE.match(stem)
    if not match:
        raise BidsStemError(
            "bids_stem must look like sub-001_ses-01_task-roam_run-02"
        )
    return match.groupdict()


def bids_output_dir(root: str | Path, stem: str, datatype: str = "beh") -> Path:
    parts = parse_bids_stem(stem)
    root_path = Path(root)
    outdir = root_path / f"sub-{parts['sub']}" / f"ses-{parts['ses']}" / datatype
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def bids_artifact_path(
    root: str | Path,
    stem: str,
    suffix: str,
    ext: str,
    datatype: str = "beh",
) -> Path:
    outdir = bids_output_dir(root=root, stem=stem, datatype=datatype)
    return outdir / f"{stem}_{suffix}.{ext}"
