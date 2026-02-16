"""微调行间距参数"""
import sys
sys.path.insert(0, "src")
import cv2


def try_row_params(path: str):
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    x_start = 100
    card_w = 238
    card_h = 120
    col_step = 255

    # 中间行确认在 y=208，尝试不同 row_step
    # row_step = y_start 使得 row1 = y_start + row_step = 208
    candidates = [
        ("D", 63, 145),  # rows: [63,183], [208,328], [353,473]
        ("E", 65, 143),  # rows: [65,185], [208,328], [351,471]
        ("F", 60, 148),  # rows: [60,180], [208,328], [356,476]
        ("G", 58, 150),  # rows: [58,178], [208,328], [358,478]
    ]

    for name, y_start, row_step in candidates:
        debug = img.copy()
        for row in range(3):
            for col in range(3):
                x = x_start + col * col_step
                y = y_start + row * row_step
                cv2.rectangle(debug, (x, y), (x + card_w, y + card_h), (0, 255, 0), 2)
                idx = row * 3 + col
                cv2.putText(debug, f"#{idx}", (x + 5, y + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        out = f"tupo_cards/grid_{name}.png"
        cv2.imwrite(out, debug)
        rows_info = [(y_start + r * row_step, y_start + r * row_step + card_h) for r in range(3)]
        gaps = [rows_info[i+1][0] - rows_info[i][1] for i in range(2)]
        print(f"  {name}: y_start={y_start}, row_step={row_step}")
        print(f"       rows: {rows_info}")
        print(f"       gaps: {gaps}")


if __name__ == "__main__":
    try_row_params(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
