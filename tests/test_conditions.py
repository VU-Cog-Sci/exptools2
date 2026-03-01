from pathlib import Path

from exptools2.core.conditions import ConditionsLoader


def test_load_tsv_conditions(tmp_path: Path) -> None:
    path = tmp_path / "conds.tsv"
    path.write_text("phase_name\tduration_s\nfoo\t0.5\n", encoding="utf8")
    rows = ConditionsLoader.load_tsv(path)
    assert rows[0]["phase_name"] == "foo"
    assert rows[0]["duration_s"] == "0.5"
