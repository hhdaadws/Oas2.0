"""在 tupo.png 上绘制检测结果"""
import sys
sys.path.insert(0, "src")
import cv2
import numpy as np
from app.modules.vision.tupo_detect import detect_tupo_grid, TupoCardState


def draw_result(img_path: str, out_path: str = "tupo_result.png"):
    img = cv2.imread(img_path)
    if img is None:
        print(f"ERROR: cannot load {img_path}")
        return

    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    result = detect_tupo_grid(img)

    # 状态对应的颜色和中文标签
    STATE_STYLE = {
        TupoCardState.DEFEATED: {
            "color": (0, 0, 200),       # 红色
            "label": "yi ji bai",
            "label_cn": "已击败",
        },
        TupoCardState.FAILED: {
            "color": (0, 165, 255),      # 橙色
            "label": "mei da guo",
            "label_cn": "没打过",
        },
        TupoCardState.NOT_CHALLENGED: {
            "color": (0, 200, 0),        # 绿色
            "label": "wei tiao zhan",
            "label_cn": "未挑战",
        },
    }

    for card in result.cards:
        style = STATE_STYLE[card.state]
        color = style["color"]
        x, y, cw, ch = card.roi

        # 绘制边框（厚度根据状态不同）
        thickness = 3 if card.state != TupoCardState.NOT_CHALLENGED else 2
        cv2.rectangle(img, (x, y), (x + cw, y + ch), color, thickness)

        # 半透明背景条
        overlay = img.copy()
        cv2.rectangle(overlay, (x, y + ch - 28), (x + cw, y + ch), color, -1)
        cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)

        # 标签文字（用拼音避免中文编码问题）
        label = style["label"]
        if card.state == TupoCardState.DEFEATED:
            detail = f"#{card.index} DEFEATED (V={card.avg_v:.0f})"
        elif card.state == TupoCardState.FAILED:
            detail = f"#{card.index} FAILED (score={card.failed_score:.2f})"
        else:
            detail = f"#{card.index} OK (V={card.avg_v:.0f})"

        cv2.putText(img, detail, (x + 5, y + ch - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

        # 顶部编号
        cv2.putText(img, f"[{card.index}]", (x + 5, y + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    # 底部统计信息
    summary = (f"Defeated: {result.defeated_count}  |  "
               f"Failed: {result.failed_count}  |  "
               f"Not Challenged: {result.not_challenged_count}")
    cv2.rectangle(img, (0, 500), (960, 540), (40, 40, 40), -1)
    cv2.putText(img, summary, (10, 528),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.imwrite(out_path, img)
    print(f"Result saved: {out_path}")


if __name__ == "__main__":
    draw_result(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
