"""精确测量结界突破网格中卡片的实际边界"""
import sys
sys.path.insert(0, "src")
import cv2
import numpy as np


def measure_grid(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 水平方向：扫描多行的灰度值，找到卡片边界
    # 取 y=120 这一行（第一行卡片中间高度）横向扫描
    for scan_y in [80, 120, 220, 260, 370, 400]:
        row_vals = gray[scan_y, :]
        # 找到灰度值的突变点（边缘）
        diff = np.abs(np.diff(row_vals.astype(int)))
        edges = np.where(diff > 30)[0]
        print(f"y={scan_y}: edges at x = {edges.tolist()[:20]}")

    print()

    # 垂直方向：扫描多列的灰度值
    for scan_x in [200, 480, 760]:
        col_vals = gray[:, scan_x]
        diff = np.abs(np.diff(col_vals.astype(int)))
        edges = np.where(diff > 30)[0]
        print(f"x={scan_x}: edges at y = {edges.tolist()[:20]}")

    print()

    # 更精确的方法：沿水平/垂直线扫描亮度，寻找卡片区域
    # 卡片区域亮度较高，间隙区域是深色边框

    # 水平切片 - 在 y=120（第一行卡片中心）
    # 绘制亮度曲线
    for scan_y in [120, 260, 400]:
        row = gray[scan_y, :]
        # 找到亮度 > 100 的连续区间（卡片内部）
        bright = row > 100
        transitions = np.diff(bright.astype(int))
        starts = np.where(transitions == 1)[0] + 1   # 暗→亮
        ends = np.where(transitions == -1)[0]          # 亮→暗

        # 确保 starts 和 ends 配对
        if len(starts) > 0 and len(ends) > 0:
            if starts[0] > ends[0]:
                ends = ends[1:]
            min_len = min(len(starts), len(ends))
            starts = starts[:min_len]
            ends = ends[:min_len]

            print(f"y={scan_y} bright regions:")
            for s, e in zip(starts, ends):
                width = e - s
                if width > 50:  # 过滤太小的区域
                    print(f"  x=[{s}, {e}] width={width}")

    print()

    # 垂直切片 - 在 x=200（第一列卡片中心）
    for scan_x in [200, 480, 760]:
        col = gray[:, scan_x]
        bright = col > 100
        transitions = np.diff(bright.astype(int))
        starts = np.where(transitions == 1)[0] + 1
        ends = np.where(transitions == -1)[0]

        if len(starts) > 0 and len(ends) > 0:
            if starts[0] > ends[0]:
                ends = ends[1:]
            min_len = min(len(starts), len(ends))
            starts = starts[:min_len]
            ends = ends[:min_len]

            print(f"x={scan_x} bright regions:")
            for s, e in zip(starts, ends):
                height = e - s
                if height > 30:
                    print(f"  y=[{s}, {e}] height={height}")

    # 保存带扫描线的调试图
    debug = img.copy()
    for y in [80, 120, 220, 260, 370, 400]:
        cv2.line(debug, (0, y), (960, y), (0, 255, 0), 1)
    for x in [200, 480, 760]:
        cv2.line(debug, (x, 0), (x, 540), (255, 0, 0), 1)
    cv2.imwrite("tupo_cards/scan_lines.png", debug)
    print("\nscan lines debug: tupo_cards/scan_lines.png")


if __name__ == "__main__":
    measure_grid(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
