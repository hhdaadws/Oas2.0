"""
截图基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import asyncio
from datetime import datetime, timedelta


class CaptureError(Exception):
    """截图异常"""
    pass


class BaseCapture(ABC):
    """截图基类"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self._cache = {}
        self._cache_expire_time = {}
        self.cache_duration = 2  # 缓存2秒
    
    @abstractmethod
    async def _capture_raw(self) -> bytes:
        """
        原始截图实现
        
        Returns:
            图像数据（PNG格式）
        
        Raises:
            CaptureError: 截图失败
        """
        pass
    
    async def capture(self, use_cache: bool = True) -> bytes:
        """
        截取屏幕图像
        
        Args:
            use_cache: 是否使用缓存
            
        Returns:
            图像数据（PNG格式）
            
        Raises:
            CaptureError: 截图失败
        """
        cache_key = f"screen_{self.device_id}"
        
        # 检查缓存
        if use_cache and cache_key in self._cache:
            expire_time = self._cache_expire_time.get(cache_key)
            if expire_time and datetime.now() < expire_time:
                return self._cache[cache_key]
        
        # 执行截图
        try:
            image_data = await self._capture_raw()
            
            # 更新缓存
            if use_cache:
                self._cache[cache_key] = image_data
                self._cache_expire_time[cache_key] = datetime.now() + timedelta(seconds=self.cache_duration)
            
            return image_data
            
        except Exception as e:
            raise CaptureError(f"截图失败: {str(e)}")
    
    async def capture_roi(self, roi: Tuple[int, int, int, int], use_cache: bool = True) -> bytes:
        """
        截取指定区域
        
        Args:
            roi: 区域坐标 (x, y, width, height)
            use_cache: 是否使用缓存
            
        Returns:
            裁剪后的图像数据
        """
        full_image = await self.capture(use_cache)
        
        # 使用PIL裁剪图像
        from PIL import Image
        import io
        
        img = Image.open(io.BytesIO(full_image))
        x, y, w, h = roi
        cropped = img.crop((x, y, x + w, y + h))
        
        # 转换回bytes
        output = io.BytesIO()
        cropped.save(output, format='PNG')
        return output.getvalue()
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        检查截图功能是否可用
        
        Returns:
            是否可用
        """
        pass
    
    def clear_cache(self):
        """清理缓存"""
        self._cache.clear()
        self._cache_expire_time.clear()