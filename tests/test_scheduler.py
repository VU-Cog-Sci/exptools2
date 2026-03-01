from exptools2.core.scheduler import NonSlipScheduler


def test_non_slip_scheduler_uses_absolute_deadlines() -> None:
    t0 = 1_000_000_000
    sched = NonSlipScheduler(t0_ns=t0, clock=lambda: t0)
    sched.start(t0)

    w1 = sched.reserve(0.1)
    w2 = sched.reserve(0.2)

    assert w1.start_ns == t0
    assert w1.end_ns == t0 + 100_000_000
    assert w2.start_ns == w1.end_ns
    assert w2.end_ns == w1.end_ns + 200_000_000
