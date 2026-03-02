from __future__ import annotations

from exptools2.core.runtime_priority import RuntimePriorityConfig, apply_runtime_priority
import exptools2.core.runtime_priority as rp


def test_runtime_priority_disabled() -> None:
    res = apply_runtime_priority(RuntimePriorityConfig(enabled=False))
    assert res.attempted is False
    assert res.applied is False
    assert res.strategy == "disabled"


def test_linux_scheduler_fallback_to_nice(monkeypatch) -> None:
    monkeypatch.setattr(rp.sys, "platform", "linux")

    def _linux_fail(_cfg):  # noqa: ANN001
        raise PermissionError("operation not permitted")

    def _nice_ok(_cfg):  # noqa: ANN001
        return True, "nice(old=0, new=-10)"

    monkeypatch.setattr(rp, "_try_linux_scheduler", _linux_fail)
    monkeypatch.setattr(rp, "_try_nice", _nice_ok)

    res = apply_runtime_priority(
        RuntimePriorityConfig(enabled=True, allow_nice_fallback=True)
    )
    assert res.attempted is True
    assert res.applied is True
    assert res.strategy == "nice"
    assert any("linux_scheduler" in err for err in res.errors)


def test_macos_qos_success_without_nice(monkeypatch) -> None:
    monkeypatch.setattr(rp.sys, "platform", "darwin")

    def _mac_ok(_cfg):  # noqa: ANN001
        return True, "macos_qos(user_interactive, relpri=0)"

    monkeypatch.setattr(rp, "_try_macos_qos", _mac_ok)

    res = apply_runtime_priority(
        RuntimePriorityConfig(enabled=True, allow_nice_fallback=False)
    )
    assert res.attempted is True
    assert res.applied is True
    assert res.strategy == "macos_qos"
    assert not res.errors

