"""
诊断脚本：验证 fk_4xtg / fk_5xtg 模板匹配能否正确区分 4x 和 5x 太鼓卡。

运行方式 (从 Oas2.0 目录):
    set PYTHONPATH=src && venv\Scripts\python tests\test_fk_4x5x_tg.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cv2
import numpy as np

from app.modules.vision.template import Match, find_all_templates, match_template
from app.modules.vision.utils import load_image

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
SCREENSHOT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "4x_5x_tg.png")
FK_4XTG = "assets/ui/templates/fk_4xtg.png"
FK_5XTG = "assets/ui/templates/fk_5xtg.png"

# ---------------------------------------------------------------------------
# 灰色段数分类常量 (与 foster.py 一致)
# ---------------------------------------------------------------------------
_TG_GRAY_S_MAX = 60
_TG_GRAY_V_MIN = 60
_TG_STRIP_ROWS = 15  # 放卡UI需要比寄养多取几行
_TG_COL_THR = 0.3
_TG_SEG_THR = 3


def classify_4xtg_5xtg(screenshot: np.ndarray, m: Match) -> tuple:
    """用底部灰色段数区分 4xtg / 5xtg，返回 (label, segments)。"""
    img_h, img_w = screenshot.shape[:2]
    y1 = max(0, m.y + m.h - _TG_STRIP_ROWS)
    y2 = min(img_h, m.y + m.h)
    x1 = max(0, m.x)
    x2 = min(img_w, m.x + m.w)
    strip = screenshot[y1:y2, x1:x2]
    if strip.size == 0:
        return "4xtg", 0

    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1]
    V = hsv[:, :, 2]
    gray_mask = (S < _TG_GRAY_S_MAX) & (V > _TG_GRAY_V_MIN)
    gray_col = gray_mask.mean(axis=0)

    segments = 0
    in_seg = False
    for v in gray_col:
        if v > _TG_COL_THR and not in_seg:
            segments += 1
            in_seg = True
        elif v <= _TG_COL_THR:
            in_seg = False

    label = "4xtg" if segments >= _TG_SEG_THR else "5xtg"
    return label, segments


def main():
    print("=" * 70)
    print("放卡 4x vs 5x 太鼓检测诊断")
    print("=" * 70)

    screenshot_abs = os.path.abspath(SCREENSHOT_PATH)
    print(f"\n截图路径: {screenshot_abs}")
    if not os.path.isfile(screenshot_abs):
        print(f"ERROR: 截图不存在")
        sys.exit(1)

    screenshot = load_image(screenshot_abs)
    print(f"截图尺寸: {screenshot.shape[1]}x{screenshot.shape[0]}")

    # ------------------------------------------------------------------
    # Part 1: 单模板最佳匹配
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Part 1: match_template — 单模板最佳匹配 (threshold=0.8)")
    print("-" * 70)

    for label, path in [("fk_4xtg", FK_4XTG), ("fk_5xtg", FK_5XTG)]:
        m = match_template(screenshot, path, threshold=0.8)
        if m:
            print(f"  {label}: score={m.score:.4f} pos=({m.x},{m.y}) "
                  f"size={m.w}x{m.h} center={m.center}")
        else:
            print(f"  {label}: 无匹配 (< 0.8)")

    # ------------------------------------------------------------------
    # Part 2: 全部匹配
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Part 2: find_all_templates — 全部匹配 (threshold=0.8)")
    print("-" * 70)

    for label, path in [("fk_4xtg", FK_4XTG), ("fk_5xtg", FK_5XTG)]:
        matches = find_all_templates(screenshot, path, threshold=0.8)
        print(f"\n  {label}: 共 {len(matches)} 个匹配")
        for i, m in enumerate(matches[:10]):
            print(f"    [{i}] score={m.score:.4f} pos=({m.x},{m.y}) center={m.center}")

    # ------------------------------------------------------------------
    # Part 3: 交叉匹配分析
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Part 3: 交叉匹配分析 — 展示混淆问题")
    print("-" * 70)

    m4 = match_template(screenshot, FK_4XTG, threshold=0.8)
    m5 = match_template(screenshot, FK_5XTG, threshold=0.8)

    if m4 and m5:
        print(f"  4xtg模板最佳匹配: score={m4.score:.4f} at ({m4.x},{m4.y})")
        print(f"  5xtg模板最佳匹配: score={m5.score:.4f} at ({m5.x},{m5.y})")
        score_diff = abs(m4.score - m5.score)
        pos_diff = abs(m4.x - m5.x) + abs(m4.y - m5.y)
        print(f"  分数差: {score_diff:.4f}")
        print(f"  位置差(曼哈顿距离): {pos_diff}px")
        if score_diff < 0.05:
            print("  ** 警告: 分数差异过小，模板几乎不可区分！")
        if pos_diff < 10:
            print("  ** 警告: 两个模板匹配到同一张卡！")

    # ------------------------------------------------------------------
    # Part 4: 灰色段数分类（foster 方法）
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Part 4: 灰色段数分类 — 对所有唯一匹配位置分类")
    print("已知: 第一张卡(+2400/h)=5x, 第二张卡(+2000/h)=4x")
    print("-" * 70)

    all_4x = find_all_templates(screenshot, FK_4XTG, threshold=0.8)
    all_5x = find_all_templates(screenshot, FK_5XTG, threshold=0.8)

    # 合并去重（15px 内视为同一位置）
    all_matches = [(m, "tpl_4x") for m in all_4x] + [(m, "tpl_5x") for m in all_5x]
    all_matches.sort(key=lambda x: x[0].score, reverse=True)

    seen = []
    unique = []
    for m, src in all_matches:
        cx, cy = m.center
        dup = False
        for sx, sy in seen:
            if abs(cx - sx) < 15 and abs(cy - sy) < 15:
                dup = True
                break
        if not dup:
            seen.append((cx, cy))
            unique.append((m, src))

    for i, (m, src) in enumerate(unique):
        label, segments = classify_4xtg_5xtg(screenshot, m)
        print(f"  [{i}] 匹配模板={src} score={m.score:.4f} "
              f"pos=({m.x},{m.y}) size={m.w}x{m.h} => 分类={label} (段数={segments})")

    # ------------------------------------------------------------------
    # Part 5: 底部条带详细分析（调试用）
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Part 5: 底部条带详细分析")
    print("-" * 70)

    for i, (m, src) in enumerate(unique):
        img_h, img_w = screenshot.shape[:2]
        y1 = max(0, m.y + m.h - _TG_STRIP_ROWS)
        y2 = min(img_h, m.y + m.h)
        x1 = max(0, m.x)
        x2 = min(img_w, m.x + m.w)
        strip = screenshot[y1:y2, x1:x2]
        print(f"\n  [{i}] strip区域: y=[{y1},{y2}], x=[{x1},{x2}], "
              f"strip形状={strip.shape}")

        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        S = hsv[:, :, 1]
        V = hsv[:, :, 2]
        gray_mask = (S < _TG_GRAY_S_MAX) & (V > _TG_GRAY_V_MIN)
        gray_col = gray_mask.mean(axis=0)
        print(f"  灰色列占比: {[f'{v:.2f}' for v in gray_col]}")

        # 保存条带图片供查看
        strip_path = os.path.join(os.path.dirname(__file__), "..", "..",
                                  f"debug_strip_{i}.png")
        cv2.imwrite(os.path.abspath(strip_path), strip)
        print(f"  条带已保存: {os.path.abspath(strip_path)}")

        # 也用不同 strip_rows 试
        for rows in [5, 10, 15, 20]:
            y1t = max(0, m.y + m.h - rows)
            strip_t = screenshot[y1t:y2, x1:x2]
            hsv_t = cv2.cvtColor(strip_t, cv2.COLOR_BGR2HSV)
            gm = (hsv_t[:, :, 1] < _TG_GRAY_S_MAX) & (hsv_t[:, :, 2] > _TG_GRAY_V_MIN)
            gc = gm.mean(axis=0)
            segs = 0
            ins = False
            for v in gc:
                if v > _TG_COL_THR and not ins:
                    segs += 1
                    ins = True
                elif v <= _TG_COL_THR:
                    ins = False
            print(f"    strip_rows={rows:2d}: segments={segs}")

    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
