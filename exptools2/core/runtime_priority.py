from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from dataclasses import dataclass, field
from typing import Any


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(slots=True)
class RuntimePriorityConfig:
    enabled: bool = False
    linux_policy: str = "fifo"
    linux_priority: int = 10
    macos_qos: str = "user_interactive"
    macos_relative_priority: int = 0
    allow_nice_fallback: bool = True
    nice_value: int = -10

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None) -> RuntimePriorityConfig:
        if not mapping:
            return cls()
        data = dict(mapping)
        return cls(
            enabled=_bool(data.get("enabled"), False),
            linux_policy=str(data.get("linux_policy", "fifo")),
            linux_priority=int(data.get("linux_priority", 10)),
            macos_qos=str(data.get("macos_qos", "user_interactive")),
            macos_relative_priority=int(data.get("macos_relative_priority", 0)),
            allow_nice_fallback=_bool(data.get("allow_nice_fallback"), True),
            nice_value=int(data.get("nice_value", -10)),
        )


@dataclass(slots=True)
class RuntimePriorityResult:
    attempted: bool
    applied: bool
    platform: str
    strategy: str
    details: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": bool(self.attempted),
            "applied": bool(self.applied),
            "platform": str(self.platform),
            "strategy": str(self.strategy),
            "details": [str(item) for item in self.details],
            "errors": [str(item) for item in self.errors],
        }


_MACOS_QOS_CLASS: dict[str, int] = {
    "background": 0x09,
    "utility": 0x11,
    "default": 0x15,
    "user_initiated": 0x19,
    "user_interactive": 0x21,
}


def _try_linux_scheduler(cfg: RuntimePriorityConfig) -> tuple[bool, str]:
    if not hasattr(os, "sched_setscheduler"):
        raise NotImplementedError("os.sched_setscheduler unavailable on this Python build")

    policy_name = str(cfg.linux_policy).strip().lower()
    if policy_name == "fifo":
        policy = os.SCHED_FIFO
    elif policy_name == "rr":
        policy = os.SCHED_RR
    else:
        raise ValueError(f"Unsupported linux_policy: {cfg.linux_policy!r} (expected 'fifo' or 'rr')")

    min_prio = int(os.sched_get_priority_min(policy))
    max_prio = int(os.sched_get_priority_max(policy))
    requested = int(cfg.linux_priority)
    priority = max(min_prio, min(requested, max_prio))

    os.sched_setscheduler(0, policy, os.sched_param(priority))
    return True, f"linux_sched_{policy_name}(priority={priority}, range={min_prio}..{max_prio})"


def _try_macos_qos(cfg: RuntimePriorityConfig) -> tuple[bool, str]:
    qos_name = str(cfg.macos_qos).strip().lower()
    qos_class = _MACOS_QOS_CLASS.get(qos_name)
    if qos_class is None:
        raise ValueError(
            f"Unsupported macos_qos: {cfg.macos_qos!r} "
            "(expected one of background|utility|default|user_initiated|user_interactive)"
        )

    lib_name = ctypes.util.find_library("System") or "libSystem.dylib"
    libc = ctypes.CDLL(lib_name, use_errno=True)
    fn = getattr(libc, "pthread_set_qos_class_self_np", None)
    if fn is None:
        raise NotImplementedError("pthread_set_qos_class_self_np unavailable")

    fn.argtypes = [ctypes.c_uint32, ctypes.c_int]
    fn.restype = ctypes.c_int
    relpri = int(cfg.macos_relative_priority)
    rc = int(fn(ctypes.c_uint32(qos_class), ctypes.c_int(relpri)))
    if rc != 0:
        err = ctypes.get_errno()
        if err:
            raise OSError(err, os.strerror(err))
        raise OSError(f"pthread_set_qos_class_self_np failed (rc={rc})")
    return True, f"macos_qos({qos_name}, relpri={relpri})"


def _try_nice(cfg: RuntimePriorityConfig) -> tuple[bool, str]:
    cur = int(os.nice(0))
    target = int(cfg.nice_value)
    delta = target - cur
    if delta == 0:
        return True, f"nice(noop={target})"
    os.nice(delta)
    new = int(os.nice(0))
    if new > cur:
        return False, f"nice(lowered_priority old={cur} new={new})"
    return True, f"nice(old={cur}, new={new})"


def apply_runtime_priority(cfg: RuntimePriorityConfig | None) -> RuntimePriorityResult:
    conf = cfg or RuntimePriorityConfig()
    platform = str(sys.platform)
    if not conf.enabled:
        return RuntimePriorityResult(
            attempted=False,
            applied=False,
            platform=platform,
            strategy="disabled",
            details=["runtime priority disabled by config"],
        )

    result = RuntimePriorityResult(
        attempted=True,
        applied=False,
        platform=platform,
        strategy="none",
    )

    if platform.startswith("linux"):
        try:
            ok, detail = _try_linux_scheduler(conf)
            if ok:
                result.applied = True
                result.strategy = "linux_scheduler"
                result.details.append(detail)
                return result
        except Exception as exc:
            result.errors.append(f"linux_scheduler: {exc.__class__.__name__}: {exc}")
    elif platform == "darwin":
        try:
            ok, detail = _try_macos_qos(conf)
            if ok:
                result.applied = True
                result.strategy = "macos_qos"
                result.details.append(detail)
                return result
        except Exception as exc:
            result.errors.append(f"macos_qos: {exc.__class__.__name__}: {exc}")
    else:
        result.errors.append(f"platform_not_supported: {platform}")

    if conf.allow_nice_fallback:
        try:
            ok, detail = _try_nice(conf)
            if ok:
                result.applied = True
                result.strategy = "nice"
                result.details.append(detail)
            else:
                result.errors.append(detail)
        except Exception as exc:
            result.errors.append(f"nice: {exc.__class__.__name__}: {exc}")

    if not result.applied and result.strategy == "none":
        result.strategy = "failed"
    return result

