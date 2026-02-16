"""
calibrate_lock2.py - 专门分析锁图标区域 (609,431) 33x37 的细节
"""
import sys
sys.path.insert(0, "src")

import cv2
import numpy as np


def analyze_lock_area(lock_path: str, unlock_path: str):
    img_lock = cv2.resize(cv2.imread(lock_path), (960, 540))
    img_unlock = cv2.resize(cv2.imread(unlock_path), (960, 540))

    # 锁图标区域（从 diff 分析得到）: pos=(609,431), size=33x37
    # 扩展 padding 看更大范围的上下文
    pad = 40
    x, y, w, h = 609, 431, 33, 37
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(960, x + w + pad), min(540, y + h + pad)

    print(f"锁图标差异区域: ({x},{y}) {w}x{h}")
    print(f"扩展分析区域: ({x1},{y1}) ~ ({x2},{y2})")

    crop_lock = img_lock[y1:y2, x1:x2]
    crop_unlock = img_unlock[y1:y2, x1:x2]

    # 放大 8 倍
    scale = 8
    big_lock = cv2.resize(crop_lock, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    big_unlock = cv2.resize(crop_unlock, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

    # 添加标签
    cv2.putText(big_lock, "LOCK", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(big_unlock, "UNLOCK", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # 在差异区域画框
    rx1, ry1 = (x - x1) * scale, (y - y1) * scale
    rx2, ry2 = (x + w - x1) * scale, (y + h - y1) * scale
    cv2.rectangle(big_lock, (rx1, ry1), (rx2, ry2), (0, 0, 255), 2)
    cv2.rectangle(big_unlock, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)

    # 横向拼接
    side = np.hstack([big_lock, big_unlock])
    cv2.imwrite("lock_area_detail.png", side)
    print(f"锁区域放大对比: lock_area_detail.png")

    # 差异图放大
    diff = cv2.absdiff(crop_lock, crop_unlock)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    diff_big = cv2.resize(diff_gray * 5, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite("lock_area_diff.png", diff_big)

    # === 分析锁图标核心区域的像素特征 ===
    roi_lock = img_lock[y:y+h, x:x+w]
    roi_unlock = img_unlock[y:y+h, x:x+w]

    # 转 HSV
    hsv_lock = cv2.cvtColor(roi_lock, cv2.COLOR_BGR2HSV)
    hsv_unlock = cv2.cvtColor(roi_unlock, cv2.COLOR_BGR2HSV)

    print(f"\n=== 锁核心区域 ({x},{y}) {w}x{h} 详细分析 ===")

    # 逐行分析
    for row in range(h):
        abs_y = y + row
        for col in range(w):
            abs_x = x + col
            pL = img_lock[abs_y, abs_x]
            pU = img_unlock[abs_y, abs_x]
            hL = hsv_lock[row, col]
            hU = hsv_unlock[row, col]
            d = int(np.max(np.abs(pL.astype(int) - pU.astype(int))))
            if d > 20:  # 只打印差异 > 20 的像素
                print(f"  ({abs_x:3d},{abs_y:3d}): "
                      f"L_rgb=({pL[2]:3d},{pL[1]:3d},{pL[0]:3d}) "
                      f"U_rgb=({pU[2]:3d},{pU[1]:3d},{pU[0]:3d}) "
                      f"L_hsv=({hL[0]:3d},{hL[1]:3d},{hL[2]:3d}) "
                      f"U_hsv=({hU[0]:3d},{hU[1]:3d},{hU[2]:3d}) "
                      f"diff={d}")

    # === 更大范围扫描：也许锁图标不只在这个区域 ===
    # 扫描底部区域 y=400~520, x=500~800
    print(f"\n=== 底部大范围差异扫描 (x:500-800, y:400-520) ===")
    bottom_lock = img_lock[400:520, 500:800]
    bottom_unlock = img_unlock[400:520, 500:800]
    bottom_diff = cv2.absdiff(bottom_lock, bottom_unlock)
    bottom_diff_gray = cv2.cvtColor(bottom_diff, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(bottom_diff_gray, 15, 255, cv2.THRESH_BINARY)
    nonzero = np.count_nonzero(thresh)
    print(f"  差异像素数: {nonzero}")

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(c)
        bx, by, bw, bh = cv2.boundingRect(c)
        if area > 10:
            print(f"  差异轮廓: abs_pos=({500+bx},{400+by}) size={bw}x{bh} area={area:.0f}")

    # 保存底部区域对比
    bottom_big_lock = cv2.resize(bottom_lock, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    bottom_big_unlock = cv2.resize(bottom_unlock, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    cv2.putText(bottom_big_lock, "LOCK", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(bottom_big_unlock, "UNLOCK", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    bottom_side = np.hstack([bottom_big_lock, bottom_big_unlock])
    cv2.imwrite("lock_bottom_compare.png", bottom_side)
    print(f"  底部区域对比图: lock_bottom_compare.png")


if __name__ == "__main__":
    analyze_lock_area("lock.png", "unlock.png")
