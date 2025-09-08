"""
图像识别模块
"""
from .template import TemplateEngine, MatchResult
from .utils import random_point_in_rect

__all__ = ["TemplateEngine", "MatchResult", "random_point_in_rect"]