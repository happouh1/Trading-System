"""Document the Phase 1D replay operational target on a chosen machine."""

from __future__ import annotations

import argparse
import platform
import time
import tracemalloc
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, Timeframe
from trading_system.replay import ReplayEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.bars <= 0:
        raise ValueError("bars must be positive")
    tracemalloc.start()
    start = datetime(2000, 1, 1, tzinfo=UTC)
    prototype = Candle(
        "AAPL",
        Timeframe.HOUR_1,
        start,
        start + timedelta(hours=1),
        date(2000, 1, 1),
        Decimal(100),
        Decimal(101),
        Decimal(99),
        Decimal(100),
        Decimal(1000),
        True,
        Decimal(1),
        "benchmark",
        "benchmark-v1",
    )
    candles = tuple(
        replace(
            prototype,
            open_time=start + timedelta(hours=index),
            close_time=start + timedelta(hours=index + 1),
            candle_id=f"benchmark-{index:09d}",
        )
        for index in range(args.bars)
    )
    began = time.perf_counter()
    records, checkpoint = ReplayEngine(lambda candle: candle.candle_id).run(candles)
    elapsed = time.perf_counter() - began
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert checkpoint is not None and len(records) == args.bars
    print(f"machine={platform.platform()}")
    print(f"python={platform.python_version()}")
    print(f"bars={args.bars}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"peak_tracemalloc_bytes={peak}")
    print(f"target_time_pass={elapsed < 600}")
    print(f"target_memory_pass={peak < 4 * 1024**3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
