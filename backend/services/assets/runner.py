"""Run every asset generator a plan routes to, in parallel.

This is the single entry point the paper pipelines call. It takes a compiled
blueprint, works out which generators own which slots, runs them concurrently
(they are independent by construction — that is the design), and returns one
merged batch plus a per-generator report for the SSE stream.

It never touches chapters, uploads or `build_chapters`. A caller that has no
uploaded content at all can still call this and get a complete Reading,
Grammar and Writing section back.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.assets.base import AssetBatchResult, AssetRequest
from services.assets.registry import (
    DEFAULT_GENERATOR,
    get_generator,
    partition_plan,
)
from services.assets.store import load_reusable_assets

logger = logging.getLogger("[ASSETS]")

#: Generators run concurrently. Three is the whole current registry; the cap
#: exists so adding a fourth language pipeline does not silently multiply
#: in-flight API requests.
_MAX_CONCURRENCY = 4


def generate_assets_for_plan(
    plan: Sequence[Any],
    *,
    subject: str,
    subject_norm: str = "",
    class_num: int = 10,
    difficulty: str = "medium",
    pool_id: str = "",
    user: Any = None,
    over_provision: int = 2,
    model: Optional[str] = None,
    reuse: bool = True,
) -> Tuple[AssetBatchResult, List[Dict[str, Any]]]:
    """Produce every non-textbook question this plan asks for.

    Returns `(merged_result, per_generator_reports)`. The reports are what the
    pipeline turns into `status` events, so a teacher watching a generation can
    see Reading and Grammar being written independently of the chapter read.
    """
    merged = AssetBatchResult()
    reports: List[Dict[str, Any]] = []

    groups = {
        name: slots
        for name, slots in partition_plan(plan).items()
        if name != DEFAULT_GENERATOR and slots
    }
    if not groups:
        return merged, reports

    existing = (
        load_reusable_assets(
            user=user,
            subject=subject,
            class_num=class_num,
            generators=list(groups),
        )
        if reuse
        else []
    )

    def _run(name: str, slots: Sequence[Any]) -> Tuple[str, AssetBatchResult, float]:
        generator = get_generator(name)
        started = time.monotonic()
        if generator is None:  # pragma: no cover - partition_plan filters these
            failed = AssetBatchResult(failures=[f"unknown generator {name!r}"])
            return name, failed, 0.0

        request = AssetRequest(
            slots=tuple(slots),
            subject=subject,
            subject_norm=subject_norm or subject,
            class_num=class_num,
            difficulty=difficulty,
            pool_id=pool_id,
            user=user,
            over_provision=over_provision,
            existing=tuple(q for q in existing if q.generator == name),
            model=model,
        )
        try:
            return name, generator.generate(request), time.monotonic() - started
        except Exception as exc:  # pragma: no cover - generators catch their own
            logger.error("Generator %s crashed: %s", name, exc, exc_info=True)
            return (
                name,
                AssetBatchResult(failures=[f"{type(exc).__name__}: {exc}"]),
                time.monotonic() - started,
            )

    with ThreadPoolExecutor(
        max_workers=min(_MAX_CONCURRENCY, len(groups))
    ) as executor:
        futures = [
            executor.submit(_run, name, slots) for name, slots in groups.items()
        ]
        for future in as_completed(futures):
            name, result, elapsed = future.result()
            merged.merge(result)
            generator = get_generator(name)
            reports.append(
                {
                    "generator": name,
                    "label": generator.label if generator else name,
                    "slots": len(groups[name]),
                    "elapsedSeconds": round(elapsed, 2),
                    **result.summary(),
                }
            )
            logger.info(
                "%s produced %d candidate(s) for %d slot(s) in %.1fs "
                "(generated=%d reused=%d failures=%s)",
                name, len(result.questions), len(groups[name]), elapsed,
                result.generated, result.reused, result.failures,
            )

    reports.sort(key=lambda r: r["generator"])
    return merged, reports
