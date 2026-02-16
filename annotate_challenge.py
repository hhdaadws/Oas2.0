"""
annotate_challenge.py - 用 tiaozhan.png 模板检测挑战标志并标注发光状态
"""
import sys
import os

sys.path.insert(0, "src")

import cv2
import numpy as np

from app.modules.vision.template import find_all_templates, Match
from app.modules.vision.grid_detect import nms_by_distance

# 使用用户提供的挑战标志模板
_TPL_CHALLENGE = "assets/ui/templates/tiaozhan.png"


def run(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    print(f"原始尺寸: {w_img}x{h_img}")
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))
        print("已缩放至 960x540")

    if not os.path.exists(_TPL_CHALLENGE):
        print(f"ERROR: 模板不存在: {_TPL_CHALLENGE}")
        return

    # 读取模板尺寸
    tpl = cv2.imread(_TPL_CHALLENGE)
    print(f"模板尺寸: {tpl.shape[1]}x{tpl.shape[0]}")

    # ── Step 1: 多阈值模板匹配扫描 ──
    print("\n--- 多阈值扫描 ---")
    for thr in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
        matches = find_all_templates(img, _TPL_CHALLENGE, threshold=thr)
        matches = nms_by_distance(matches, min_distance=25)
        print(f"  threshold={thr}: {len(matches)} 个匹配")
        for i, m in enumerate(matches):
            print(f"    [{i}] center={m.center}, score={m.score:.3f}, size={m.w}x{m.h}")

    # ── Step 2: 用 0.85 阈值做最终检测（真标志~0.96，误匹配<0.78）──
    threshold = 0.85
    matches = find_all_templates(img, _TPL_CHALLENGE, threshold=threshold)
    matches = nms_by_distance(matches, min_distance=25)

    print(f"\n最终检测 (threshold={threshold}): {len(matches)} 个标志")

    # ── Step 3: HSV 亮度分析 + 标注 ──
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    debug_img = img.copy()

    # 环形遮罩参数 - 根据模板大小自适应
    tpl_h, tpl_w = tpl.shape[:2]
    tpl_r = max(tpl_w, tpl_h) // 2
    INNER_R = tpl_r + 2      # 内圈 = 模板半径 + 小间距
    OUTER_R = tpl_r + 18     # 外圈 = 覆盖光环区域
    BRIGHT_V_THR = 180

    print(f"环形遮罩: inner_r={INNER_R}, outer_r={OUTER_R} (模板半径={tpl_r})")

    for i, m in enumerate(matches):
        cx, cy = m.center

        # 环形遮罩分析
        x1 = max(0, cx - OUTER_R)
        y1 = max(0, cy - OUTER_R)
        x2 = min(960, cx + OUTER_R + 1)
        y2 = min(540, cy + OUTER_R + 1)

        roi = hsv[y1:y2, x1:x2]
        lcx, lcy = cx - x1, cy - y1
        rh, rw = roi.shape[:2]

        mask = np.zeros((rh, rw), dtype=np.uint8)
        cv2.circle(mask, (lcx, lcy), OUTER_R, 255, -1)
        cv2.circle(mask, (lcx, lcy), INNER_R, 0, -1)

        v_pixels = roi[:, :, 2][mask > 0]
        s_pixels = roi[:, :, 1][mask > 0]

        if len(v_pixels) > 0:
            avg_v = float(np.mean(v_pixels))
            v_std = float(np.std(v_pixels))
            bright_ratio = float(np.sum(v_pixels >= BRIGHT_V_THR)) / len(v_pixels)
            avg_s = float(np.mean(s_pixels))
        else:
            avg_v = v_std = bright_ratio = avg_s = 0.0

        # 判定
        is_glow = bright_ratio >= 0.15 and avg_v >= 120
        label = "GLOW" if is_glow else "NORMAL"

        print(f"  标志[{i}]: center=({cx},{cy}), score={m.score:.3f}")
        print(f"    avg_V={avg_v:.1f}, v_std={v_std:.1f}, bright_ratio={bright_ratio:.3f}, "
              f"avg_S={avg_s:.1f} → {label}")

        # 标注
        glow_color = (0, 255, 255)   # 黄色 = 发光
        normal_color = (0, 200, 0)   # 绿色 = 普通
        color = glow_color if is_glow else normal_color

        # 模板匹配框
        cv2.rectangle(debug_img, (m.x, m.y), (m.x + m.w, m.y + m.h), (255, 0, 0), 2)
        # 内圈
        cv2.circle(debug_img, (cx, cy), INNER_R, (0, 255, 0), 1)
        # 外圈
        cv2.circle(debug_img, (cx, cy), OUTER_R, (0, 0, 255), 1)
        # 中心点
        cv2.circle(debug_img, (cx, cy), 4, color, -1)
        # 标签
        text = f"#{i} {label}"
        cv2.putText(debug_img, text, (cx - 30, cy - OUTER_R - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
        # 数据
        data_text = f"V={avg_v:.0f} BR={bright_ratio:.2f} S={m.score:.2f}"
        cv2.putText(debug_img, data_text, (cx - 50, cy + OUTER_R + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    # 保存
    base = os.path.splitext(path)[0]
    out = f"{base}_annotated.png"
    cv2.imwrite(out, debug_img)
    print(f"\n标注图已保存: {out}")
    print(f"  蓝框=模板匹配, 绿圈=内圈(排除), 红圈=外圈(采样)")
    print(f"  黄点+GLOW=发光标志, 绿点+NORMAL=普通标志")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <screenshot.png>")
        sys.exit(1)
    run(sys.argv[1])
