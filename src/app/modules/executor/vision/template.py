"""
模板匹配引擎
"""
import cv2
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from ....core.logger import logger


@dataclass
class MatchResult:
    """模板匹配结果"""
    found: bool
    confidence: float
    center_x: int
    center_y: int
    top_left_x: int
    top_left_y: int
    bottom_right_x: int
    bottom_right_y: int
    width: int
    height: int


class TemplateEngine:
    """模板匹配引擎"""
    
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir
        self.template_cache = {}
        self.logger = logger.bind(module="TemplateEngine")
    
    def load_template(self, template_name: str) -> Optional[np.ndarray]:
        """
        加载模板图片
        
        Args:
            template_name: 模板文件名
            
        Returns:
            模板图像数组，失败返回None
        """
        if template_name in self.template_cache:
            return self.template_cache[template_name]
        
        try:
            import os
            template_path = os.path.join(self.templates_dir, template_name)
            
            if not os.path.exists(template_path):
                self.logger.warning(f"模板文件不存在: {template_path}")
                return None
            
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template is None:
                self.logger.warning(f"无法读取模板文件: {template_path}")
                return None
            
            # 缓存模板
            self.template_cache[template_name] = template
            self.logger.debug(f"模板加载成功: {template_name}, 尺寸: {template.shape}")
            
            return template
            
        except Exception as e:
            self.logger.error(f"加载模板失败: {template_name}, 错误: {str(e)}")
            return None
    
    def match_template(self, screenshot: bytes, template_name: str, threshold: float = 0.8) -> MatchResult:
        """
        在大图中匹配小图模板
        
        Args:
            screenshot: 截图数据（PNG格式）
            template_name: 模板文件名
            threshold: 匹配阈值 (0.0-1.0)
            
        Returns:
            匹配结果
        """
        try:
            # 将bytes转换为cv2图像
            nparr = np.frombuffer(screenshot, np.uint8)
            main_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if main_img is None:
                return MatchResult(
                    found=False, confidence=0.0,
                    center_x=0, center_y=0,
                    top_left_x=0, top_left_y=0,
                    bottom_right_x=0, bottom_right_y=0,
                    width=0, height=0
                )
            
            # 加载模板
            template = self.load_template(template_name)
            if template is None:
                return MatchResult(
                    found=False, confidence=0.0,
                    center_x=0, center_y=0,
                    top_left_x=0, top_left_y=0,
                    bottom_right_x=0, bottom_right_y=0,
                    width=0, height=0
                )
            
            # 执行模板匹配
            result = cv2.matchTemplate(main_img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # 检查是否满足阈值
            if max_val >= threshold:
                # 计算匹配区域
                template_h, template_w = template.shape[:2]
                top_left_x, top_left_y = max_loc
                bottom_right_x = top_left_x + template_w
                bottom_right_y = top_left_y + template_h
                center_x = top_left_x + template_w // 2
                center_y = top_left_y + template_h // 2
                
                self.logger.debug(
                    f"模板匹配成功: {template_name}, "
                    f"置信度: {max_val:.3f}, "
                    f"位置: ({center_x}, {center_y})"
                )
                
                return MatchResult(
                    found=True,
                    confidence=max_val,
                    center_x=center_x,
                    center_y=center_y,
                    top_left_x=top_left_x,
                    top_left_y=top_left_y,
                    bottom_right_x=bottom_right_x,
                    bottom_right_y=bottom_right_y,
                    width=template_w,
                    height=template_h
                )
            else:
                self.logger.debug(
                    f"模板匹配失败: {template_name}, "
                    f"最高置信度: {max_val:.3f}, "
                    f"要求阈值: {threshold}"
                )
                
                return MatchResult(
                    found=False, confidence=max_val,
                    center_x=0, center_y=0,
                    top_left_x=0, top_left_y=0,
                    bottom_right_x=0, bottom_right_y=0,
                    width=0, height=0
                )
            
        except Exception as e:
            self.logger.error(f"模板匹配异常: {template_name}, 错误: {str(e)}")
            return MatchResult(
                found=False, confidence=0.0,
                center_x=0, center_y=0,
                top_left_x=0, top_left_y=0,
                bottom_right_x=0, bottom_right_y=0,
                width=0, height=0
            )
    
    def match_multiple_templates(self, screenshot: bytes, template_names: list, threshold: float = 0.8) -> list:
        """
        匹配多个模板
        
        Args:
            screenshot: 截图数据
            template_names: 模板文件名列表
            threshold: 匹配阈值
            
        Returns:
            匹配结果列表
        """
        results = []
        for template_name in template_names:
            result = self.match_template(screenshot, template_name, threshold)
            if result.found:
                results.append((template_name, result))
        
        # 按置信度排序
        results.sort(key=lambda x: x[1].confidence, reverse=True)
        return results
    
    def find_best_match(self, screenshot: bytes, template_names: list, threshold: float = 0.8) -> Tuple[Optional[str], Optional[MatchResult]]:
        """
        找到最佳匹配的模板
        
        Args:
            screenshot: 截图数据
            template_names: 模板文件名列表
            threshold: 匹配阈值
            
        Returns:
            (最佳模板名, 匹配结果) 或 (None, None)
        """
        best_template = None
        best_result = None
        best_confidence = 0.0
        
        for template_name in template_names:
            result = self.match_template(screenshot, template_name, threshold)
            if result.found and result.confidence > best_confidence:
                best_template = template_name
                best_result = result
                best_confidence = result.confidence
        
        return best_template, best_result