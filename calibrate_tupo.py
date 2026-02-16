"""
calibrate_tupo.py - 结界突破网格状态检测校准工具

用途:
  1. 可视化 9 个卡片的 ROI 和采样区域
  2. 提取每个卡片的 HSV/BGR 统计数据
  3. 辅助确定模板匹配和 HSV 阈值
  4. 生成带标注的调试图
  5. 从已击败卡片裁切印章模板

使用方法:
  python calibrate_tupo.py tupo.png
  python calibrate_tupo.py --crop tupo.png 0
"""
import sys
import os

sys.path.insert(0, "src")

import cv2
import numpy as np


# ── 网格布局预估常量（960×540 分辨率）──
GRID_X_START = 72
GRID_Y_START = 52
CARD_W = 270
CARD_H = 138
COL_GAP = 5
ROW_GAP = 5

# 印章采样区域（相对于卡片左上角）
STAMP_X_OFF = 80
STAMP_Y_OFF = 30
STAMP_W = 120
STAMP_H = 80

# 右上角标志采样区域（相对于卡片左上角）
CORNER_X_OFF = 230  # 靠近右边
CORNER_Y_OFF = 0    # 顶部
CORNER_W = 40
CORNER_H = 30


def get_card_rois():
    """计算 9 个卡片的 ROI。"""
    cards = []
    for row in range(3):
        for col in range(3):
            x = GRID_X_START + col * (CARD_W + COL_GAP)
            y = GRID_Y_START + row * (CARD_H + ROW_GAP)
            cards.append({
                "index": row * 3 + col,
                "row": row,
                "col": col,
                "card_roi": (x, y, CARD_W, CARD_H),
                "center": (x + CARD_W // 2, y + CARD_H // 2),
                "stamp_roi": (x + STAMP_X_OFF, y + STAMP_Y_OFF, STAMP_W, STAMP_H),
                "corner_roi": (x + CORNER_X_OFF, y + CORNER_Y_OFF, CORNER_W, CORNER_H),
            })
    return cards


def analyze_tupo(path: str):
    """分析结界突破截图中 9 个卡片的颜色特征。"""
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
    debug_img = img.copy()

    cards = get_card_rois()

    print(f"\n{'='*70}")
    print(f"分析: {path}")
    print(f"{'='*70}")

    for card in cards:
        idx = card["index"]
        cx, cy, cw, ch = card["card_roi"]
        sx, sy, sw, sh = card["stamp_roi"]
        rx, ry, rw, rh = card["corner_roi"]

        # 卡片整体 HSV
        card_hsv = hsv[cy:cy+ch, cx:cx+cw]
        c_h = np.mean(card_hsv[:, :, 0])
        c_s = np.mean(card_hsv[:, :, 1])
        c_v = np.mean(card_hsv[:, :, 2])

        # 印章区域 HSV
        stamp_hsv = hsv[sy:sy+sh, sx:sx+sw]
        s_h = np.mean(stamp_hsv[:, :, 0])
        s_s = np.mean(stamp_hsv[:, :, 1])
        s_v = np.mean(stamp_hsv[:, :, 2])

        # 印章区域 BGR
        stamp_bgr = img[sy:sy+sh, sx:sx+sw]
        s_b = np.mean(stamp_bgr[:, :, 0])
        s_g = np.mean(stamp_bgr[:, :, 1])
        s_r = np.mean(stamp_bgr[:, :, 2])

        # 右上角区域 HSV
        corner_hsv = hsv[ry:ry+rh, rx:rx+rw]
        r_h = np.mean(corner_hsv[:, :, 0])
        r_s = np.mean(corner_hsv[:, :, 1])
        r_v = np.mean(corner_hsv[:, :, 2])

        # 右上角区域 BGR
        corner_bgr = img[ry:ry+rh, rx:rx+rw]
        r_b = np.mean(corner_bgr[:, :, 0])
        r_g = np.mean(corner_bgr[:, :, 1])
        r_r = np.mean(corner_bgr[:, :, 2])

        # 右上角灰度亮度
        corner_gray = cv2.cvtColor(corner_bgr, cv2.COLOR_BGR2GRAY)
        r_brightness = np.mean(corner_gray)

        print(f"\n  卡片[{idx}] (row={card['row']}, col={card['col']}):")
        print(f"    卡片ROI:  ({cx}, {cy}, {cw}, {ch})  center=({card['center'][0]}, {card['center'][1]})")
        print(f"    卡片HSV:  H={c_h:.1f}, S={c_s:.1f}, V={c_v:.1f}")
        print(f"    印章ROI:  ({sx}, {sy}, {sw}, {sh})")
        print(f"    印章HSV:  H={s_h:.1f}, S={s_s:.1f}, V={s_v:.1f}")
        print(f"    印章BGR:  B={s_b:.1f}, G={s_g:.1f}, R={s_r:.1f}")
        print(f"    角落ROI:  ({rx}, {ry}, {rw}, {rh})")
        print(f"    角落HSV:  H={r_h:.1f}, S={r_s:.1f}, V={r_v:.1f}")
        print(f"    角落BGR:  B={r_b:.1f}, G={r_g:.1f}, R={r_r:.1f}")
        print(f"    角落亮度: {r_brightness:.1f}")

        # 在调试图上绘制
        # 卡片边框（绿色）
        cv2.rectangle(debug_img, (cx, cy), (cx+cw, cy+ch), (0, 255, 0), 1)
        # 印章采样区（黄色）
        cv2.rectangle(debug_img, (sx, sy), (sx+sw, sy+sh), (0, 255, 255), 2)
        # 右上角采样区（红色）
        cv2.rectangle(debug_img, (rx, ry), (rx+rw, ry+rh), (0, 0, 255), 2)
        # 编号标注
        cv2.putText(debug_img, f"#{idx}", (cx+5, cy+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # 保存调试图
    base = os.path.splitext(path)[0]
    out = f"{base}_tupo_debug.png"
    cv2.imwrite(out, debug_img)
    print(f"\n调试图已保存: {out}")
    print("  绿框 = 卡片边界, 黄框 = 印章采样区, 红框 = 右上角采样区")


def crop_stamp_template(path: str, card_index: int = 0):
    """从指定已击败卡片中裁切印章模板。"""
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    cards = get_card_rois()
    card = cards[card_index]
    sx, sy, sw, sh = card["stamp_roi"]
    stamp = img[sy:sy+sh, sx:sx+sw]

    out = "assets/ui/templates/tupo_defeated.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, stamp)
    print(f"印章模板已保存: {out} (从卡片[{card_index}]裁切, ROI=({sx},{sy},{sw},{sh}))")

    # 同时裁切右上角标志
    rx, ry, rw, rh = card["corner_roi"]
    corner = img[ry:ry+rh, rx:rx+rw]
    out2 = "assets/ui/templates/tupo_failed_mark.png"
    cv2.imwrite(out2, corner)
    print(f"角落标志已保存: {out2} (从卡片[{card_index}]裁切, ROI=({rx},{ry},{rw},{rh}))")


def crop_corner_from_failed(path: str, card_index: int = 1):
    """从没打过的卡片裁切右上角标志。"""
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    cards = get_card_rois()
    card = cards[card_index]
    rx, ry, rw, rh = card["corner_roi"]
    corner = img[ry:ry+rh, rx:rx+rw]

    out = "assets/ui/templates/tupo_failed_mark.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, corner)
    print(f"没打过标志已保存: {out} (从卡片[{card_index}]裁切, ROI=({rx},{ry},{rw},{rh}))")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python calibrate_tupo.py <screenshot.png>              # 分析")
        print("  python calibrate_tupo.py --crop <screenshot.png> [idx] # 裁切已击败印章")
        print("  python calibrate_tupo.py --corner <screenshot.png> [idx] # 裁切没打过角落标志")
        sys.exit(1)

    if sys.argv[1] == "--crop":
        idx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        crop_stamp_template(sys.argv[2], idx)
    elif sys.argv[1] == "--corner":
        idx = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        crop_corner_from_failed(sys.argv[2], idx)
    else:
        for path in sys.argv[1:]:
            analyze_tupo(path)
