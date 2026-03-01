from exptools2.core import make_bids_stem, parse_bids_stem


def test_make_and_parse_bids_stem() -> None:
    stem = make_bids_stem(sub="001", ses="01", task="roam", run="02")
    assert stem == "sub-001_ses-01_task-roam_run-02"

    parts = parse_bids_stem(stem)
    assert parts == {"sub": "001", "ses": "01", "task": "roam", "run": "02"}
