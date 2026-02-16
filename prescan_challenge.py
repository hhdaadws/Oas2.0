"""
prescan_challenge.py - 预扫描探索截图，无需模板即可检测候选挑战标志

通过亮度/颜色特征定位可能的挑战标志区域，标注并保存调试图。
用于在没有模板时先定位标志位置，以便裁切模板。
"""
import sys
import os

sys.path.insert(0, "src")

import cv2
import numpy as np


def prescan(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    print(f"原始尺寸: {w_img}x{h_img}")
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))
        print("已缩放至 960x540")

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    debug_img = img.copy()

    # 排除顶部和底部 UI 区域，只扫描游戏区域
    game_y_start = 50
    game_y_end = 480

    # 方法1：全局亮度分析 - 找到明亮小区域
    v_channel = hsv[:, :, 2]
    game_v = v_channel[game_y_start:game_y_end, :]

    print(f"\n游戏区域 V 通道统计:")
    print(f"  mean={np.mean(game_v):.1f}, std={np.std(game_v):.1f}")
    print(f"  min={np.min(game_v)}, max={np.max(game_v)}")

    # 方法2：用高阈值二值化找亮区域
    # 挑战标志通常比背景亮很多
    for v_thr in [180, 200, 220]:
        bright_mask = np.zeros_like(v_channel)
        bright_mask[game_y_start:game_y_end, :] = \
            (v_channel[game_y_start:game_y_end, :] > v_thr).astype(np.uint8) * 255

        # 形态学操作：关运算填洞 + 开运算去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 过滤：面积适中的候选区域（挑战标志大概 100-3000 像素面积）
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 50 < area < 5000:
                x, y, w, h = cv2.boundingRect(cnt)
                # 长宽比不要太极端
                aspect = max(w, h) / (min(w, h) + 1)
                if aspect < 4:
                    m = cv2.moments(cnt)
                    if m["m00"] > 0:
                        cx = int(m["m10"] / m["m00"])
                        cy = int(m["m01"] / m["m00"])
                        candidates.append({
                            "center": (cx, cy),
                            "bbox": (x, y, w, h),
                            "area": area,
                            "aspect": aspect,
                        })

        print(f"\n  V>{v_thr}: {len(candidates)} 个候选区域")
        for i, c in enumerate(candidates):
            cx, cy = c["center"]
            x, y, w, h = c["bbox"]
            print(f"    [{i}] center=({cx},{cy}), bbox=({x},{y},{w},{h}), "
                  f"area={c['area']:.0f}, aspect={c['aspect']:.2f}")

    # 方法3：综合标注 - 使用 V>200 的结果
    bright_mask = np.zeros_like(v_channel)
    bright_mask[game_y_start:game_y_end, :] = \
        (v_channel[game_y_start:game_y_end, :] > 190).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    idx = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 50 < area < 5000:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = max(w, h) / (min(w, h) + 1)
            if aspect < 4:
                m = cv2.moments(cnt)
                if m["m00"] > 0:
                    cx = int(m["m10"] / m["m00"])
                    cy = int(m["m01"] / m["m00"])

                    # 在调试图上绘制
                    cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.circle(debug_img, (cx, cy), 3, (0, 0, 255), -1)
                    cv2.putText(debug_img, f"#{idx} ({cx},{cy}) a={area:.0f}",
                                (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                                (0, 255, 255), 1)

                    # 裁切候选区域（带 padding）
                    pad = 10
                    crop_x1 = max(0, x - pad)
                    crop_y1 = max(0, y - pad)
                    crop_x2 = min(960, x + w + pad)
                    crop_y2 = min(540, y + h + pad)
                    crop = img[crop_y1:crop_y2, crop_x1:crop_x2]

                    crop_dir = "prescan_crops"
                    os.makedirs(crop_dir, exist_ok=True)
                    cv2.imwrite(f"{crop_dir}/candidate_{idx}.png", crop)

                    idx += 1

    # 同时画网格辅助定位
    for gx in range(0, 960, 100):
        cv2.line(debug_img, (gx, 0), (gx, 540), (50, 50, 50), 1)
        cv2.putText(debug_img, str(gx), (gx+2, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100, 100, 100), 1)
    for gy in range(0, 540, 100):
        cv2.line(debug_img, (0, gy), (960, gy), (50, 50, 50), 1)
        cv2.putText(debug_img, str(gy), (2, gy+12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100, 100, 100), 1)

    base = os.path.splitext(path)[0]
    out = f"{base}_prescan.png"
    cv2.imwrite(out, debug_img)
    print(f"\n标注图已保存: {out}")
    print(f"候选裁切已保存到 prescan_crops/ 目录")
    print(f"\n下一步: 确认哪个候选是挑战标志后，使用以下命令裁切模板:")
    print(f"  python calibrate_explore_glow.py --crop {path} <x> <y> <w> <h>")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <screenshot.png>")
        sys.exit(1)
    for p in sys.argv[1:]:
        prescan(p)
