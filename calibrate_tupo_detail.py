"""详细分析 tupo.png - 裁切每个独立卡片和多个子区域"""
import sys
import os
sys.path.insert(0, "src")
import cv2
import numpy as np


def detailed_analysis(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: cannot load {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    os.makedirs("tupo_cards", exist_ok=True)

    # 先裁切整个网格区域看看
    grid = img[40:490, 60:910]
    cv2.imwrite("tupo_cards/grid_area.png", grid)

    # 预估的卡片位置 - 尝试多个偏移来找到最佳对齐
    GRID_X_START = 72
    GRID_Y_START = 52
    CARD_W = 270
    CARD_H = 138
    COL_GAP = 5
    ROW_GAP = 5

    for row in range(3):
        for col in range(3):
            idx = row * 3 + col
            x = GRID_X_START + col * (CARD_W + COL_GAP)
            y = GRID_Y_START + row * (CARD_H + ROW_GAP)
            card = img[y:y+CARD_H, x:x+CARD_W]
            cv2.imwrite(f"tupo_cards/card_{idx}_r{row}c{col}.png", card)

            # 裁切卡片的不同区域
            # 左侧1/3（头像区域）
            left = card[:, :90]
            cv2.imwrite(f"tupo_cards/card_{idx}_left.png", left)

            # 中间1/3（文字/印章区域）
            mid = card[:, 90:180]
            cv2.imwrite(f"tupo_cards/card_{idx}_mid.png", mid)

            # 右侧1/3
            right = card[:, 180:]
            cv2.imwrite(f"tupo_cards/card_{idx}_right.png", right)

            # 上半部分
            top = card[:69, :]
            cv2.imwrite(f"tupo_cards/card_{idx}_top.png", top)

            # 下半部分
            bottom = card[69:, :]
            cv2.imwrite(f"tupo_cards/card_{idx}_bottom.png", bottom)

            # 右上角（多种大小）
            corner_small = card[:20, -30:]
            cv2.imwrite(f"tupo_cards/card_{idx}_corner_small.png", corner_small)
            corner_mid = card[:40, -50:]
            cv2.imwrite(f"tupo_cards/card_{idx}_corner_mid.png", corner_mid)
            corner_large = card[:60, -80:]
            cv2.imwrite(f"tupo_cards/card_{idx}_corner_large.png", corner_large)

    print("已保存所有卡片和子区域到 tupo_cards/ 目录")
    print(f"共 {9} 张卡片 × 8 个子区域 = {72} 张图片")


if __name__ == "__main__":
    detailed_analysis(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
