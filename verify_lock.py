"""验证锁定模板匹配效果"""
import sys
sys.path.insert(0, "src")

from app.modules.vision.template import match_template

_TPL_LOCK = "assets/ui/templates/lock_jiekai.png"

# ROI 限制在锁图标附近区域以提高准确性和性能
_LOCK_ROI = (570, 400, 100, 80)  # (x, y, w, h)


def test_match(image_path: str, expected_locked: bool):
    import cv2
    img = cv2.resize(cv2.imread(image_path), (960, 540))

    # 全图匹配
    m_full = match_template(img, _TPL_LOCK, threshold=0.5)
    score_full = m_full.score if m_full else 0
    print(f"\n{image_path} (期望: {'锁定' if expected_locked else '未锁定'})")
    print(f"  全图匹配: score={score_full:.4f}, pos={m_full.center if m_full else 'None'}")

    # ROI 匹配
    rx, ry, rw, rh = _LOCK_ROI
    roi_img = img[ry:ry+rh, rx:rx+rw]
    m_roi = match_template(roi_img, _TPL_LOCK, threshold=0.5)
    score_roi = m_roi.score if m_roi else 0
    print(f"  ROI匹配:  score={score_roi:.4f}")

    # 用不同阈值测试
    for th in [0.6, 0.7, 0.8, 0.85, 0.9]:
        m = match_template(roi_img, _TPL_LOCK, threshold=th)
        print(f"    阈值={th}: {'匹配' if m else '未匹配'}")


if __name__ == "__main__":
    test_match("lock.png", expected_locked=True)
    test_match("unlock.png", expected_locked=False)
