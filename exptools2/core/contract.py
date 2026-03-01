from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import RunRequest, ScannerTriggerMode

CONTRACT_VERSION = "1.1"
VALID_SCANNER_MODES = {"none", "key", "ttl", "lsl"}
VALID_STATUS = {"RUN_STARTED", "PHASE_STARTED", "EVENT", "SYNC", "RUN_ENDED"}


class ContractValidationError(ValueError):
    pass


def validate_scanner_trigger_mode(mode: ScannerTriggerMode) -> None:
    if mode.mode not in VALID_SCANNER_MODES:
        raise ContractValidationError(
            f"scanner_trigger_mode.mode must be one of {sorted(VALID_SCANNER_MODES)}"
        )
    if not isinstance(mode.params, dict):
        raise ContractValidationError("scanner_trigger_mode.params must be a dict")


def validate_run_request(request: RunRequest) -> None:
    if request.contract_version != CONTRACT_VERSION:
        raise ContractValidationError(
            f"contract_version={request.contract_version!r} is unsupported; expected {CONTRACT_VERSION!r}"
        )

    if not request.bids_stem:
        raise ContractValidationError("bids_stem is required")

    if not isinstance(request.condition_row, dict):
        raise ContractValidationError("condition_row must be a dict")

    if not isinstance(request.seed, int):
        raise ContractValidationError("seed must be an int")

    if not isinstance(request.t0_ns, int) or request.t0_ns <= 0:
        raise ContractValidationError("t0_ns must be a positive int")

    validate_scanner_trigger_mode(request.scanner_trigger_mode)


def request_to_payload(request: RunRequest) -> dict[str, Any]:
    payload = asdict(request)
    return payload


def load_contract_schema() -> dict[str, Any]:
    schema_path = Path(__file__).with_name("contract_v1_1.schema.json")
    return json.loads(schema_path.read_text(encoding="utf8"))
