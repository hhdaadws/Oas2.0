"""裁剪锁定状态模板并保存"""
import cv2
import numpy as np

img = cv2.resize(cv2.imread("lock.png"), (960, 540))

# 锁图标区域 - 从 diff 分析得到 (609,431) 33x37
# 稍微扩展一点以包含完整的锁图标
x, y, w, h = 607, 428, 37, 42
crop = img[y:y+h, x:x+w]

# 保存模板
cv2.imwrite("assets/ui/templates/lock_jiekai.png", crop)
print(f"已保存锁定模板: assets/ui/templates/lock_jiekai.png ({w}x{h})")

# 也保存一个放大版用于目视确认
big = cv2.resize(crop, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
cv2.imwrite("lock_template_preview.png", big)
print(f"模板预览: lock_template_preview.png")

# 同时裁剪 unlock 状态的同位置区域做对比
img_u = cv2.resize(cv2.imread("unlock.png"), (960, 540))
crop_u = img_u[y:y+h, x:x+w]
cv2.imwrite("unlock_template_preview.png",
            cv2.resize(crop_u, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST))
print(f"解锁预览: unlock_template_preview.png")
