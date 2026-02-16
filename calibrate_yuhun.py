"""校准脚本 v3：用校准后的参数验证检测结果。"""
import sys
sys.path.insert(0, "src")

from app.modules.vision.yuhun_detect import detect_yuhun_levels, find_highest_unlocked_level
import cv2


def test_image(path: str):
    print(f"\n{'='*60}")
    print(f"测试: {path}")
    print(f"{'='*60}")

    levels = detect_yuhun_levels(path)
    for lv in levels:
        print(
            f"  层级{lv.index}: {lv.state.value:10s}  "
            f"center={lv.center}  "
            f"HSV=({lv.avg_hsv[0]:5.1f}, {lv.avg_hsv[1]:5.1f}, {lv.avg_hsv[2]:6.1f})"
        )

    best = find_highest_unlocked_level(path)
    if best:
        print(f"\n  最高解锁层级: 第{best.index}层 ({best.state.value})")
    else:
        print(f"\n  未找到解锁层级")

    # 生成带标注的调试图
    img = cv2.imread(path)
    if img is not None:
        h_img, w_img = img.shape[:2]
        if (w_img, h_img) != (960, 540):
            img = cv2.resize(img, (960, 540))
        for lv in levels:
            x, y, w, h = lv.roi
            color = {
                "selected": (0, 255, 255),   # 黄色
                "unlocked": (0, 255, 0),      # 绿色
                "locked": (0, 0, 255),        # 红色
            }[lv.state.value]
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                img, f"L{lv.index}:{lv.state.value}",
                (x + w + 5, y + h // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
            )
        out = path.replace(".png", "_final.png")
        cv2.imwrite(out, img)
        print(f"  调试图: {out}")


if __name__ == "__main__":
    test_image("1222.png")
    test_image("1333.png")
