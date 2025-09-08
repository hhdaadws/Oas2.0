"""
时间工具模块 - 统一使用北京时间
"""
from datetime import datetime, timedelta, time
import pytz

# 北京时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def now_beijing() -> datetime:
    """获取北京时间的当前时间"""
    return datetime.now(BEIJING_TZ)

def utc_to_beijing(utc_dt: datetime) -> datetime:
    """将UTC时间转换为北京时间"""
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    return utc_dt.astimezone(BEIJING_TZ)

def beijing_to_utc(beijing_dt: datetime) -> datetime:
    """将北京时间转换为UTC时间（用于数据库存储）"""
    if beijing_dt.tzinfo is None:
        beijing_dt = BEIJING_TZ.localize(beijing_dt)
    return beijing_dt.astimezone(pytz.UTC).replace(tzinfo=None)

def parse_beijing_time(time_str: str) -> datetime:
    """解析北京时间字符串（格式：2025-09-03 21:00）"""
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    return BEIJING_TZ.localize(dt)

def format_beijing_time(dt: datetime) -> str:
    """格式化为北京时间字符串"""
    if dt.tzinfo is None:
        # 假设是UTC时间
        dt = pytz.UTC.localize(dt)
    beijing_dt = dt.astimezone(BEIJING_TZ)
    return beijing_dt.strftime("%Y-%m-%d %H:%M")

def is_time_reached(target_time_str: str) -> bool:
    """检查是否到达指定的北京时间"""
    if not target_time_str:
        return False
    
    try:
        target_dt = parse_beijing_time(target_time_str)
        current_dt = now_beijing()
        return current_dt >= target_dt
    except ValueError:
        return False

def add_hours_to_beijing_time(time_str: str, hours: int) -> str:
    """在北京时间基础上增加小时数"""
    try:
        dt = parse_beijing_time(time_str)
        new_dt = dt + timedelta(hours=hours)
        return format_beijing_time(new_dt)
    except ValueError:
        # 如果解析失败，从当前时间开始计算
        current = now_beijing()
        new_dt = current + timedelta(hours=hours)
        return format_beijing_time(new_dt)

def get_next_fixed_time(current_time_str: str, fixed_times: list) -> str:
    """
    获取下一个固定时间点
    例如：12:00, 18:00 -> 如果当前在12-18之间，返回今天18:00，否则返回明天12:00
    """
    try:
        current_dt = parse_beijing_time(current_time_str) if current_time_str else now_beijing()
    except ValueError:
        current_dt = now_beijing()
    
    current_time = current_dt.time()
    
    # 查找今天剩余的时间点
    for time_str in fixed_times:
        hour, minute = map(int, time_str.split(':'))
        target_time = time(hour, minute)
        if current_time < target_time:
            # 找到今天的下一个时间点
            today = current_dt.date()
            next_dt = BEIJING_TZ.localize(datetime.combine(today, target_time))
            return format_beijing_time(next_dt)
    
    # 今天的时间点都过了，返回明天第一个时间点
    tomorrow = current_dt.date() + timedelta(days=1)
    hour, minute = map(int, fixed_times[0].split(':'))
    target_time = time(hour, minute)
    next_dt = BEIJING_TZ.localize(datetime.combine(tomorrow, target_time))
    return format_beijing_time(next_dt)