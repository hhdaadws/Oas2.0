"""用 Canny 边缘检测找到卡片的精确边界"""
import sys
sys.path.insert(0, "src")
import cv2
import numpy as np


def find_borders(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 用 Canny 检测边缘
    edges = cv2.Canny(gray, 50, 150)

    # 找到垂直线（卡片的左右边界）
    # 沿水平方向统计每一列的边缘点密度
    col_density = np.sum(edges > 0, axis=0).astype(float)
    # 平滑
    kernel = np.ones(3) / 3
    col_smooth = np.convolve(col_density, kernel, mode='same')

    # 找到垂直边缘密度高的列
    v_threshold = np.mean(col_smooth) + np.std(col_smooth) * 1.5
    v_peaks = np.where(col_smooth > v_threshold)[0]

    # 聚合相邻的列
    v_borders = []
    if len(v_peaks) > 0:
        group = [v_peaks[0]]
        for i in range(1, len(v_peaks)):
            if v_peaks[i] - v_peaks[i-1] <= 3:
                group.append(v_peaks[i])
            else:
                v_borders.append(int(np.mean(group)))
                group = [v_peaks[i]]
        v_borders.append(int(np.mean(group)))

    print("垂直边界（卡片左右边框）:")
    for x in v_borders:
        print(f"  x={x}")

    # 找到水平线（卡片的上下边界）
    row_density = np.sum(edges > 0, axis=1).astype(float)
    row_smooth = np.convolve(row_density, kernel, mode='same')

    h_threshold = np.mean(row_smooth) + np.std(row_smooth) * 1.5
    h_peaks = np.where(row_smooth > h_threshold)[0]

    h_borders = []
    if len(h_peaks) > 0:
        group = [h_peaks[0]]
        for i in range(1, len(h_peaks)):
            if h_peaks[i] - h_peaks[i-1] <= 3:
                group.append(h_peaks[i])
            else:
                h_borders.append(int(np.mean(group)))
                group = [h_peaks[i]]
        h_borders.append(int(np.mean(group)))

    print("\n水平边界（卡片上下边框）:")
    for y in h_borders:
        print(f"  y={y}")

    # 绘制检测到的边界线
    debug = img.copy()
    for x in v_borders:
        cv2.line(debug, (x, 0), (x, 540), (0, 255, 0), 1)
    for y in h_borders:
        cv2.line(debug, (0, y), (960, y), (0, 0, 255), 1)
    cv2.imwrite("tupo_cards/borders_debug.png", debug)
    print("\n边界调试图: tupo_cards/borders_debug.png")

    # 也保存边缘检测图
    cv2.imwrite("tupo_cards/edges.png", edges)

    # 手动方法：沿特定行/列扫描像素值
    # 检查各列在 y=120 处的像素值，找深色边框
    print("\n手动扫描 y=120 行的灰度值（每5px采样）:")
    row120 = gray[120, :]
    for x in range(0, 960, 5):
        val = row120[x]
        marker = "|" if val < 80 else " "
        if x % 50 == 0:
            print(f"  x={x:3d}: {val:3d} {marker}")

    print("\n手动扫描 x=480 列的灰度值（每5px采样）:")
    col480 = gray[:, 480]
    for y in range(40, 480, 5):
        val = col480[y]
        marker = "-" if val < 80 else " "
        if y % 10 == 0:
            print(f"  y={y:3d}: {val:3d} {marker}")


if __name__ == "__main__":
    find_borders(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
