"""精确裁切没打过警告图标"""
import sys
import os
sys.path.insert(0, "src")
import cv2
import numpy as np


def crop_warn_icon(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    # Card 1 的位置
    card1_x = 347
    card1_y = 52

    # 从 corner_large 分析：icon在 card[:60, -80:] 中的 x≈10-38, y≈2-32
    # 即相对于卡片: x_offset=190+10=200, y_offset=2
    # 绝对坐标: x=347+200=547, y=52+2=54

    # 尝试多个候选位置
    candidates = [
        ("warn_a", 547, 54, 30, 32),
        ("warn_b", 542, 52, 35, 35),
        ("warn_c", 540, 50, 40, 40),
        ("warn_d", 545, 53, 32, 33),
    ]

    os.makedirs("tupo_cards", exist_ok=True)
    for name, x, y, w, h in candidates:
        crop = img[y:y+h, x:x+w]
        out = f"tupo_cards/{name}.png"
        cv2.imwrite(out, crop)
        print(f"  {name}: ({x}, {y}, {w}, {h}) -> {out}")

    # 用最佳候选保存为模板
    # 从 card_1_corner_large 的视觉分析，warn_c 应该最能涵盖整个图标
    best_x, best_y, best_w, best_h = 540, 50, 40, 40
    warn = img[best_y:best_y+best_h, best_x:best_x+best_w]
    cv2.imwrite("assets/ui/templates/tupo_failed_mark.png", warn)
    print(f"\n最终模板: assets/ui/templates/tupo_failed_mark.png ({best_x}, {best_y}, {best_w}, {best_h})")

    # 对比：在其他卡片的相同位置裁切
    for idx, (card_x, card_y) in [
        (0, (72, 52)),    # 已击败
        (4, (347, 195)),  # 未挑战
        (6, (72, 338)),   # 未挑战
    ]:
        rx = card_x + (best_x - card1_x)
        ry = card_y + (best_y - card1_y)
        comp = img[ry:ry+best_h, rx:rx+best_w]
        out = f"tupo_cards/warn_comp_card{idx}.png"
        cv2.imwrite(out, comp)
        print(f"  对比 card{idx}: ({rx}, {ry}, {best_w}, {best_h}) -> {out}")


if __name__ == "__main__":
    crop_warn_icon(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
