"""用 fail.png 在 tupo.png 中搜索匹配位置"""
import sys
sys.path.insert(0, "src")
import cv2
from app.modules.vision.template import match_template, find_all_templates


def test_match(img_path, tpl_path):
    img = cv2.imread(img_path)
    if img is None:
        print(f"ERROR: cannot load {img_path}")
        return

    h, w = img.shape[:2]
    if (w, h) != (960, 540):
        img = cv2.resize(img, (960, 540))

    # 全图搜索
    matches = find_all_templates(img, tpl_path, threshold=0.5)
    print(f"模板: {tpl_path}")
    print(f"全图匹配 (threshold=0.5): {len(matches)} 个")
    for i, m in enumerate(matches):
        print(f"  [{i}] pos=({m.x}, {m.y}) size=({m.w}x{m.h}) center={m.center} score={m.score:.3f}")

    # 也试试破字模板
    matches2 = find_all_templates(img, "assets/ui/templates/tupo_defeated.png", threshold=0.5)
    print(f"\n破字模板全图匹配 (threshold=0.5): {len(matches2)} 个")
    for i, m in enumerate(matches2):
        print(f"  [{i}] pos=({m.x}, {m.y}) size=({m.w}x{m.h}) center={m.center} score={m.score:.3f}")

    # 在调试图上标注
    debug = img.copy()
    for m in matches:
        cv2.rectangle(debug, (m.x, m.y), (m.x+m.w, m.y+m.h), (0, 255, 255), 2)
        cv2.putText(debug, f"{m.score:.2f}", (m.x, m.y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for m in matches2:
        cv2.rectangle(debug, (m.x, m.y), (m.x+m.w, m.y+m.h), (0, 0, 255), 2)
        cv2.putText(debug, f"{m.score:.2f}", (m.x, m.y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.imwrite("tupo_cards/match_debug.png", debug)
    print("\n调试图已保存: tupo_cards/match_debug.png")


if __name__ == "__main__":
    test_match("tupo.png", "fail.png")
