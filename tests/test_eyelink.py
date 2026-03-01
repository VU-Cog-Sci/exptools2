from exptools2.eyelink.client import normalize_remote_edf_name, stem_to_remote_edf


def test_normalize_remote_edf_name() -> None:
    assert normalize_remote_edf_name("sub-001_ses-01_task-demo_run-01") == "SUB001SE.EDF"
    assert normalize_remote_edf_name("abc") == "ABC.EDF"
    assert normalize_remote_edf_name("___") == "EXPRUN01.EDF"


def test_stem_to_remote_edf_is_8_char_max() -> None:
    edf = stem_to_remote_edf("sub-123_ses-02_task-verylongname_run-99")
    assert edf.endswith(".EDF")
    assert len(edf.split(".")[0]) <= 8

