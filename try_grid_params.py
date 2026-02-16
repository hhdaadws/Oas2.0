"""尝试不同网格参数，画框可视化对比"""
import sys
sys.path.insert(0, "src")
import cv2
import numpy as np


def try_params(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    # 候选参数组
    params = {
        "A": {"x_start": 95, "y_start": 68, "card_w": 245, "card_h": 124, "col_step": 260, "row_step": 140},
        "B": {"x_start": 100, "y_start": 70, "card_w": 238, "card_h": 120, "col_step": 255, "row_step": 138},
        "C": {"x_start": 97, "y_start": 66, "card_w": 242, "card_h": 126, "col_step": 258, "row_step": 142},
    }

    for name, p in params.items():
        debug = img.copy()
        for row in range(3):
            for col in range(3):
                x = p["x_start"] + col * p["col_step"]
                y = p["y_start"] + row * p["row_step"]
                cv2.rectangle(debug, (x, y), (x + p["card_w"], y + p["card_h"]), (0, 255, 0), 2)
                idx = row * 3 + col
                cv2.putText(debug, f"#{idx}", (x + 5, y + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        out = f"tupo_cards/grid_{name}.png"
        cv2.imwrite(out, debug)
        print(f"  {name}: {p} -> {out}")


if __name__ == "__main__":
    try_params(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
