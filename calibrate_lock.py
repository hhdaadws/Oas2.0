"""
calibrate_lock.py - 分析 lock.png 和 unlock.png 的像素级差异，
定位锁图标位置及两种状态的视觉特征。
"""
import sys
sys.path.insert(0, "src")

import cv2
import numpy as np


def analyze_diff(lock_path: str, unlock_path: str):
    # 1. 加载并统一尺寸
    img_lock = cv2.imread(lock_path)
    img_unlock = cv2.imread(unlock_path)
    if img_lock is None or img_unlock is None:
        print("ERROR: 无法加载图片")
        return

    target_size = (960, 540)
    img_lock = cv2.resize(img_lock, target_size)
    img_unlock = cv2.resize(img_unlock, target_size)

    # 2. 计算绝对差异
    diff = cv2.absdiff(img_lock, img_unlock)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

    print(f"差异图统计: min={diff_gray.min()}, max={diff_gray.max()}, "
          f"mean={diff_gray.mean():.2f}, nonzero={np.count_nonzero(diff_gray)}")

    # 3. 阈值处理 - 找到差异显著的区域
    for thresh_val in [10, 20, 30, 50]:
        _, thresh = cv2.threshold(diff_gray, thresh_val, 255, cv2.THRESH_BINARY)
        nonzero = np.count_nonzero(thresh)
        print(f"  阈值 {thresh_val}: 差异像素数={nonzero}")

    # 用较低阈值找到所有差异区域
    _, thresh = cv2.threshold(diff_gray, 15, 255, cv2.THRESH_BINARY)

    # 形态学操作去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # 4. 找差异区域的轮廓
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"\n找到 {len(contours)} 个差异区域:")

    # 按面积排序
    contour_info = []
    for c in contours:
        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)
        contour_info.append((area, x, y, w, h, c))

    contour_info.sort(key=lambda t: t[0], reverse=True)

    # 5. 分析每个差异区域
    debug_img = img_lock.copy()
    for i, (area, x, y, w, h, c) in enumerate(contour_info[:20]):
        if area < 5:
            continue
        print(f"\n  区域 {i+1}: pos=({x},{y}), size={w}x{h}, area={area:.0f}")

        # 提取两种状态下该区域的颜色特征
        roi_lock = img_lock[y:y+h, x:x+w]
        roi_unlock = img_unlock[y:y+h, x:x+w]

        # BGR 均值
        mean_lock_bgr = cv2.mean(roi_lock)[:3]
        mean_unlock_bgr = cv2.mean(roi_unlock)[:3]
        print(f"    lock   BGR均值: ({mean_lock_bgr[0]:.0f}, {mean_lock_bgr[1]:.0f}, {mean_lock_bgr[2]:.0f})")
        print(f"    unlock BGR均值: ({mean_unlock_bgr[0]:.0f}, {mean_unlock_bgr[1]:.0f}, {mean_unlock_bgr[2]:.0f})")

        # HSV 均值
        hsv_lock = cv2.cvtColor(roi_lock, cv2.COLOR_BGR2HSV)
        hsv_unlock = cv2.cvtColor(roi_unlock, cv2.COLOR_BGR2HSV)
        mean_lock_hsv = cv2.mean(hsv_lock)[:3]
        mean_unlock_hsv = cv2.mean(hsv_unlock)[:3]
        print(f"    lock   HSV均值: ({mean_lock_hsv[0]:.0f}, {mean_lock_hsv[1]:.0f}, {mean_lock_hsv[2]:.0f})")
        print(f"    unlock HSV均值: ({mean_unlock_hsv[0]:.0f}, {mean_unlock_hsv[1]:.0f}, {mean_unlock_hsv[2]:.0f})")

        # 灰度均值
        gray_lock = cv2.cvtColor(roi_lock, cv2.COLOR_BGR2GRAY)
        gray_unlock = cv2.cvtColor(roi_unlock, cv2.COLOR_BGR2GRAY)
        print(f"    lock   灰度均值: {gray_lock.mean():.1f}")
        print(f"    unlock 灰度均值: {gray_unlock.mean():.1f}")

        # 在调试图上标注
        cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 0, 255), 2)
        cv2.putText(debug_img, f"#{i+1} ({w}x{h})",
                    (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # 6. 保存调试图
    # 差异热力图
    diff_colored = cv2.applyColorMap((diff_gray * 5).clip(0, 255).astype(np.uint8),
                                      cv2.COLORMAP_JET)
    cv2.imwrite("lock_diff_heatmap.png", diff_colored)
    print(f"\n差异热力图已保存: lock_diff_heatmap.png")

    # 标注差异区域的 lock 图
    cv2.imwrite("lock_diff_annotated.png", debug_img)
    print(f"标注图已保存: lock_diff_annotated.png")

    # 两图拼接对比（上 lock 下 unlock）
    comparison = np.vstack([img_lock, img_unlock])
    cv2.imwrite("lock_comparison.png", comparison)
    print(f"对比图已保存: lock_comparison.png")

    # 7. 如果有明显的差异区域，裁剪放大展示
    if contour_info:
        # 取最大的差异区域，扩展 ROI 用于详细分析
        area, x, y, w, h, c = contour_info[0]
        pad = 20
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(960, x + w + pad)
        y2 = min(540, y + h + pad)

        crop_lock = img_lock[y1:y2, x1:x2]
        crop_unlock = img_unlock[y1:y2, x1:x2]

        # 放大 4 倍
        scale = 4
        crop_lock_big = cv2.resize(crop_lock, None, fx=scale, fy=scale,
                                    interpolation=cv2.INTER_NEAREST)
        crop_unlock_big = cv2.resize(crop_unlock, None, fx=scale, fy=scale,
                                      interpolation=cv2.INTER_NEAREST)

        # 横向拼接
        side_by_side = np.hstack([crop_lock_big, crop_unlock_big])
        cv2.imwrite("lock_detail_compare.png", side_by_side)
        print(f"\n最大差异区域放大对比: lock_detail_compare.png")
        print(f"  ROI: ({x1},{y1}) ~ ({x2},{y2})")

        # 逐像素打印差异区域的具体数值
        print(f"\n  === 最大差异区域像素详情 ===")
        diff_roi = diff_gray[y1:y2, x1:x2]
        ys, xs = np.where(diff_roi > 15)
        for py, px in zip(ys[:30], xs[:30]):
            abs_x, abs_y = x1 + px, y1 + py
            pix_lock = img_lock[abs_y, abs_x]
            pix_unlock = img_unlock[abs_y, abs_x]
            d = diff_gray[abs_y, abs_x]
            print(f"    ({abs_x:3d},{abs_y:3d}): "
                  f"lock=({pix_lock[2]:3d},{pix_lock[1]:3d},{pix_lock[0]:3d}) "
                  f"unlock=({pix_unlock[2]:3d},{pix_unlock[1]:3d},{pix_unlock[0]:3d}) "
                  f"diff={d}")


if __name__ == "__main__":
    analyze_diff("lock.png", "unlock.png")
