import pytest

from exptools2.core import RunRequest, ScannerTriggerMode
from exptools2.core.contract import ContractValidationError, validate_run_request


def test_validate_request_success() -> None:
    req = RunRequest(
        bids_stem="sub-001_ses-01_task-roam_run-02",
        condition_row={"x": 1},
        seed=1,
        t0_ns=1,
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )
    validate_run_request(req)


def test_validate_request_rejects_invalid_mode() -> None:
    req = RunRequest(
        bids_stem="sub-001_ses-01_task-roam_run-02",
        condition_row={},
        seed=1,
        t0_ns=1,
        scanner_trigger_mode=ScannerTriggerMode(mode="bad"),
    )
    with pytest.raises(ContractValidationError):
        validate_run_request(req)
