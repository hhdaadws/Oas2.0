"""精确像素级扫描，找到卡片内容区域的真实边界"""
import sys
sys.path.insert(0, "src")
import cv2
import numpy as np


def precise_scan(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 策略：在卡片内容区域取多条扫描线，找到灰度突变点
    # 用未挑战卡片（亮度高）更容易找到边界

    # ── 精确水平扫描：逐像素找卡片左右边界 ──
    print("=== 水平扫描（找列边界）===")
    # 扫描 3 行的中心高度
    for label, scan_y in [("row0_mid", 140), ("row1_mid", 280), ("row2_mid", 420)]:
        row = gray[scan_y, :]
        # 找到 >120 的连续区间
        runs = []
        start = None
        for x in range(960):
            if row[x] > 120:
                if start is None:
                    start = x
            else:
                if start is not None and x - start > 100:
                    runs.append((start, x - 1))
                start = None
        if start is not None and 960 - start > 100:
            runs.append((start, 959))

        print(f"\n  {label} (y={scan_y}):")
        for i, (s, e) in enumerate(runs):
            print(f"    region {i}: x=[{s}, {e}], width={e - s + 1}")

    # ── 精确垂直扫描：逐像素找卡片上下边界 ──
    print("\n=== 垂直扫描（找行边界）===")
    # 扫描 3 列的中心 x 坐标（使用未挑战卡片的列）
    for label, scan_x in [("col1_mid", 480), ("col2_mid", 740)]:
        col = gray[:, scan_x]
        runs = []
        start = None
        for y in range(540):
            if col[y] > 120:
                if start is None:
                    start = y
            else:
                if start is not None and y - start > 50:
                    runs.append((start, y - 1))
                start = None
        if start is not None and 540 - start > 50:
            runs.append((start, 539))

        print(f"\n  {label} (x={scan_x}):")
        for i, (s, e) in enumerate(runs):
            print(f"    region {i}: y=[{s}, {e}], height={e - s + 1}")

    # ── 更精确：找到边框颜色（深棕色/黑色）的连续垂直/水平线 ──
    # 卡片边框通常是暗色的 (<80)
    print("\n=== 暗色列统计（边框位置）===")
    # 在 y=[60, 480] 范围内，统计每列灰度 <80 的像素比例
    region = gray[60:480, :]
    dark_ratio = np.mean(region < 80, axis=0)
    # 找到暗色比例 >0.5 的列（可能是垂直边框）
    dark_cols = np.where(dark_ratio > 0.4)[0]
    if len(dark_cols) > 0:
        # 聚合相邻列
        groups = []
        group = [dark_cols[0]]
        for i in range(1, len(dark_cols)):
            if dark_cols[i] - dark_cols[i-1] <= 2:
                group.append(dark_cols[i])
            else:
                groups.append((min(group), max(group)))
                group = [dark_cols[i]]
        groups.append((min(group), max(group)))
        print("  暗色列区域（可能是卡片间的垂直分割线）:")
        for s, e in groups:
            print(f"    x=[{s}, {e}], width={e - s + 1}")

    print("\n=== 暗色行统计（边框位置）===")
    region2 = gray[:, 100:860]
    dark_ratio_h = np.mean(region2 < 80, axis=1)
    dark_rows = np.where(dark_ratio_h > 0.4)[0]
    if len(dark_rows) > 0:
        groups = []
        group = [dark_rows[0]]
        for i in range(1, len(dark_rows)):
            if dark_rows[i] - dark_rows[i-1] <= 2:
                group.append(dark_rows[i])
            else:
                groups.append((min(group), max(group)))
                group = [dark_rows[i]]
        groups.append((min(group), max(group)))
        print("  暗色行区域（可能是卡片间的水平分割线）:")
        for s, e in groups:
            print(f"    y=[{s}, {e}], width={e - s + 1}")


if __name__ == "__main__":
    precise_scan(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
