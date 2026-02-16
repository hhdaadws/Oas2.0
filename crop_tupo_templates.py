"""精确裁切结界突破状态标志模板"""
import sys
import os
sys.path.insert(0, "src")
import cv2
import numpy as np


def crop_templates(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: cannot load {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    os.makedirs("assets/ui/templates", exist_ok=True)

    # 网格布局
    GRID_X_START = 72
    GRID_Y_START = 52
    CARD_W = 270
    CARD_H = 138
    COL_GAP = 5
    ROW_GAP = 5

    # ── 裁切"破"字印章（从已击败卡片0） ──
    # "破"字在卡片右侧，大约从卡片右边 x_offset=200 开始，占 70px 宽
    # y 方向大约从卡片中部偏上 y_offset=20 开始，高约 100px
    card0_x = GRID_X_START + 0 * (CARD_W + COL_GAP)
    card0_y = GRID_Y_START + 0 * (CARD_H + ROW_GAP)

    # 裁切"破"字区域 - 从右侧裁切
    stamp_x = card0_x + 210
    stamp_y = card0_y + 15
    stamp_w = 55
    stamp_h = 80
    stamp = img[stamp_y:stamp_y+stamp_h, stamp_x:stamp_x+stamp_w]
    cv2.imwrite("assets/ui/templates/tupo_defeated.png", stamp)
    print(f"破字印章已保存: assets/ui/templates/tupo_defeated.png")
    print(f"  ROI: ({stamp_x}, {stamp_y}, {stamp_w}, {stamp_h})")
    # 也保存一个大一点的用于对比
    cv2.imwrite("tupo_cards/stamp_defeated_crop.png", stamp)

    # ── 裁切"!"警告图标（从没打过卡片1） ──
    card1_x = GRID_X_START + 1 * (CARD_W + COL_GAP)
    card1_y = GRID_Y_START + 0 * (CARD_H + ROW_GAP)

    # "!" 菱形图标在卡片右上方
    warn_x = card1_x + 220
    warn_y = card1_y + 2
    warn_w = 30
    warn_h = 35
    warn = img[warn_y:warn_y+warn_h, warn_x:warn_x+warn_w]
    cv2.imwrite("assets/ui/templates/tupo_failed_mark.png", warn)
    print(f"警告图标已保存: assets/ui/templates/tupo_failed_mark.png")
    print(f"  ROI: ({warn_x}, {warn_y}, {warn_w}, {warn_h})")
    cv2.imwrite("tupo_cards/stamp_failed_crop.png", warn)

    # ── 验证：也裁切一个未挑战卡片的相同区域作对比 ──
    card4_x = GRID_X_START + 1 * (CARD_W + COL_GAP)
    card4_y = GRID_Y_START + 1 * (CARD_H + ROW_GAP)

    # 相同位置裁切用于对比
    comp_stamp_x = card4_x + 210
    comp_stamp_y = card4_y + 15
    comp_stamp = img[comp_stamp_y:comp_stamp_y+stamp_h, comp_stamp_x:comp_stamp_x+stamp_w]
    cv2.imwrite("tupo_cards/comp_not_challenged_right.png", comp_stamp)

    comp_warn_x = card4_x + 220
    comp_warn_y = card4_y + 2
    comp_warn = img[comp_warn_y:comp_warn_y+warn_h, comp_warn_x:comp_warn_x+warn_w]
    cv2.imwrite("tupo_cards/comp_not_challenged_corner.png", comp_warn)

    print("\n对比图已保存到 tupo_cards/ 目录")

    # ── 在全图上绘制标注 ──
    debug = img.copy()
    # 标注已击败破字区域（红色）
    cv2.rectangle(debug, (stamp_x, stamp_y), (stamp_x+stamp_w, stamp_y+stamp_h), (0, 0, 255), 2)
    cv2.putText(debug, "PO", (stamp_x, stamp_y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # 标注没打过警告图标（黄色）
    cv2.rectangle(debug, (warn_x, warn_y), (warn_x+warn_w, warn_y+warn_h), (0, 255, 255), 2)
    cv2.putText(debug, "WARN", (warn_x, warn_y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    cv2.imwrite("tupo_cards/debug_templates.png", debug)
    print("调试标注图已保存: tupo_cards/debug_templates.png")


if __name__ == "__main__":
    crop_templates(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
