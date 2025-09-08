"""
图像处理工具函数
"""
import random
from typing import Tuple


def random_point_in_rect(x: int, y: int, width: int, height: int, margin: int = 5) -> Tuple[int, int]:
    """
    在指定矩形区域内生成随机点
    
    Args:
        x: 矩形左上角X坐标
        y: 矩形左上角Y坐标
        width: 矩形宽度
        height: 矩形高度
        margin: 边缘留白（避免点击到边缘）
        
    Returns:
        (random_x, random_y) 随机点坐标
    """
    # 确保有足够的空间留白
    if width <= margin * 2 or height <= margin * 2:
        # 如果区域太小，直接返回中心点
        return x + width // 2, y + height // 2
    
    # 在留白区域内生成随机点
    random_x = random.randint(x + margin, x + width - margin)
    random_y = random.randint(y + margin, y + height - margin)
    
    return random_x, random_y


def random_point_in_match_result(match_result, margin: int = 5) -> Tuple[int, int]:
    """
    在模板匹配结果区域内生成随机点
    
    Args:
        match_result: MatchResult对象
        margin: 边缘留白
        
    Returns:
        (random_x, random_y) 随机点坐标
    """
    return random_point_in_rect(
        match_result.top_left_x,
        match_result.top_left_y,
        match_result.width,
        match_result.height,
        margin
    )


def add_random_offset(x: int, y: int, max_offset: int = 3) -> Tuple[int, int]:
    """
    为坐标添加随机偏移，模拟人类点击
    
    Args:
        x: 原X坐标
        y: 原Y坐标
        max_offset: 最大偏移像素
        
    Returns:
        (new_x, new_y) 添加偏移后的坐标
    """
    offset_x = random.randint(-max_offset, max_offset)
    offset_y = random.randint(-max_offset, max_offset)
    
    return x + offset_x, y + offset_y


def ensure_point_in_screen(x: int, y: int, screen_width: int = 1920, screen_height: int = 1080) -> Tuple[int, int]:
    """
    确保点击坐标在屏幕范围内
    
    Args:
        x: X坐标
        y: Y坐标
        screen_width: 屏幕宽度
        screen_height: 屏幕高度
        
    Returns:
        (safe_x, safe_y) 安全的坐标
    """
    safe_x = max(0, min(x, screen_width - 1))
    safe_y = max(0, min(y, screen_height - 1))
    
    return safe_x, safe_y


def calculate_click_delay() -> float:
    """
    计算随机的点击延迟，模拟人类操作
    
    Returns:
        延迟时间（秒）
    """
    # 生成0.1-0.5秒的随机延迟
    return random.uniform(0.1, 0.5)