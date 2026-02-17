"""异步模板匹配包装器。

将同步的 match_template / find_all_templates offload 到计算线程池，
避免阻塞事件循环。
"""
from __future__ import annotations

import functools
from typing import List, Optional

from ...core.thread_pool import run_in_compute
from .template import Match, match_template as _sync_match, find_all_templates as _sync_find_all
from .utils import ImageLike


async def async_match_template(
    image: ImageLike,
    template: ImageLike,
    *,
    threshold: Optional[float] = None,
) -> Optional[Match]:
    """异步版本的 match_template，在计算线程池中执行。"""
    return await run_in_compute(
        functools.partial(_sync_match, image, template, threshold=threshold)
    )


async def async_find_all_templates(
    image: ImageLike,
    template: ImageLike,
    *,
    threshold: Optional[float] = None,
) -> List[Match]:
    """异步版本的 find_all_templates，在计算线程池中执行。"""
    return await run_in_compute(
        functools.partial(_sync_find_all, image, template, threshold=threshold)
    )


__all__ = ["async_match_template", "async_find_all_templates"]
