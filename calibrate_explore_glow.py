"""
calibrate_explore_glow.py - 探索地图挑战标志发光检测校准工具

用途:
  1. 从截图中查找所有挑战标志并分析周围亮度特征
  2. 可视化环形采样区域（内圈/外圈）
  3. 输出每个标志的 HSV 统计数据，辅助确定阈值
  4. 生成带标注的调试图
  5. 从截图裁切挑战标志模板

使用方法:
  python calibrate_explore_glow.py <screenshot.png>                     # 分析
  python calibrate_explore_glow.py --crop <screenshot.png> x y w h     # 裁切模板
  python calibrate_explore_glow.py --sweep <screenshot.png>            # 参数扫描
"""
import sys
import os

sys.path.insert(0, "src")

import cv2
import numpy as np

from app.modules.vision.template import find_all_templates, Match
from app.modules.vision.grid_detect import nms_by_distance
from app.modules.vision.utils import load_image

# ── 默认参数 ──
_TPL_CHALLENGE = "assets/ui/templates/tansuo_tiaozhan.png"
_CHALLENGE_THRESHOLD = 0.70

# 环形遮罩半径（像素）
_RING_INNER_R = 18
_RING_OUTER_R = 32

# 亮度分析阈值（初始估计，通过本脚本校准）
_BRIGHT_V_THRESHOLD = 180


def create_ring_mask(h: int, w: int, cx: int, cy: int,
                     inner_r: int, outer_r: int) -> np.ndarray:
    """创建环形遮罩（内圈透明，外环白色）。"""
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (cx, cy), outer_r, 255, -1)
    cv2.circle(mask, (cx, cy), inner_r, 0, -1)
    return mask


def analyze_marker_glow(hsv_img: np.ndarray, cx: int, cy: int,
                        inner_r: int = _RING_INNER_R,
                        outer_r: int = _RING_OUTER_R,
                        bright_v_thr: int = _BRIGHT_V_THRESHOLD):
    """分析标志周围环形区域的亮度特征。

    Returns:
        dict: avg_v, bright_ratio, v_std, avg_s, pixel_count
    """
    h, w = hsv_img.shape[:2]

    # 裁剪环形区域的包围矩形
    x1 = max(0, cx - outer_r)
    y1 = max(0, cy - outer_r)
    x2 = min(w, cx + outer_r + 1)
    y2 = min(h, cy + outer_r + 1)

    roi = hsv_img[y1:y2, x1:x2]
    local_cx = cx - x1
    local_cy = cy - y1

    rh, rw = roi.shape[:2]
    mask = create_ring_mask(rh, rw, local_cx, local_cy, inner_r, outer_r)

    v_pixels = roi[:, :, 2][mask > 0]
    s_pixels = roi[:, :, 1][mask > 0]

    if len(v_pixels) == 0:
        return {"avg_v": 0, "bright_ratio": 0, "v_std": 0, "avg_s": 0, "pixel_count": 0}

    avg_v = float(np.mean(v_pixels))
    v_std = float(np.std(v_pixels))
    bright_count = int(np.sum(v_pixels >= bright_v_thr))
    bright_ratio = bright_count / len(v_pixels)
    avg_s = float(np.mean(s_pixels))

    return {
        "avg_v": avg_v,
        "bright_ratio": bright_ratio,
        "v_std": v_std,
        "avg_s": avg_s,
        "pixel_count": len(v_pixels),
    }


def analyze_screenshot(path: str, template: str = _TPL_CHALLENGE,
                       threshold: float = _CHALLENGE_THRESHOLD):
    """分析探索截图中所有挑战标志的发光特征。"""
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    print(f"原始尺寸: {w_img}x{h_img}")
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))
        print("已缩放至 960x540")

    if not os.path.exists(template):
        print(f"ERROR: 模板文件不存在: {template}")
        print("请先使用 --crop 模式裁切模板:")
        print(f"  python {sys.argv[0]} --crop <screenshot.png> x y w h")
        return

    # 模板匹配找到所有标志
    matches = find_all_templates(img, template, threshold=threshold)
    matches = nms_by_distance(matches)

    print(f"\n找到 {len(matches)} 个挑战标志 (threshold={threshold})")

    if not matches:
        print("未找到任何标志。尝试降低阈值或检查模板。")
        return

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    debug_img = img.copy()

    print(f"\n{'='*75}")
    print(f"分析: {path}")
    print(f"{'='*75}")

    for i, m in enumerate(matches):
        cx, cy = m.center

        stats = analyze_marker_glow(hsv, cx, cy)

        print(f"\n  标志[{i}]:")
        print(f"    center=({cx}, {cy}), match_score={m.score:.3f}")
        print(f"    avg_V={stats['avg_v']:.1f}, bright_ratio={stats['bright_ratio']:.3f}, "
              f"v_std={stats['v_std']:.1f}")
        print(f"    avg_S={stats['avg_s']:.1f}, pixel_count={stats['pixel_count']}")

        # 判定（初始阈值，待校准）
        is_glow = stats["bright_ratio"] >= 0.25 and stats["avg_v"] >= 140
        label = "GLOWING" if is_glow else "NORMAL"
        print(f"    → {label}")

        # 绘制调试标注
        color = (0, 255, 255) if is_glow else (200, 200, 200)  # 黄色=发光，灰色=普通
        cv2.circle(debug_img, (cx, cy), _RING_INNER_R, (0, 255, 0), 1)   # 内圈绿色
        cv2.circle(debug_img, (cx, cy), _RING_OUTER_R, (0, 0, 255), 1)   # 外圈红色
        cv2.circle(debug_img, (cx, cy), 3, color, -1)                     # 中心点
        # 模板匹配框
        cv2.rectangle(debug_img, (m.x, m.y), (m.x + m.w, m.y + m.h), (255, 0, 0), 1)
        # 文字标注
        text = f"#{i} {label} V={stats['avg_v']:.0f} BR={stats['bright_ratio']:.2f}"
        cv2.putText(debug_img, text,
                    (cx - 60, cy + _RING_OUTER_R + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

    # 保存调试图
    base = os.path.splitext(path)[0]
    out = f"{base}_glow_debug.png"
    cv2.imwrite(out, debug_img)
    print(f"\n调试图已保存: {out}")
    print("  绿圈 = 内圈(排除标志), 红圈 = 外圈(采样光环), 蓝框 = 模板匹配")
    print("  黄点 = GLOWING, 灰点 = NORMAL")


def crop_template(path: str, x: int, y: int, w: int, h: int):
    """从截图中裁切挑战标志模板。"""
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    template = img[y:y+h, x:x+w]
    out = _TPL_CHALLENGE
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, template)
    print(f"模板已保存: {out} (ROI=({x},{y},{w},{h}), size={w}x{h})")

    # 同时保存预览图
    preview = img.copy()
    cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 0, 255), 2)
    preview_path = f"{os.path.splitext(path)[0]}_crop_preview.png"
    cv2.imwrite(preview_path, preview)
    print(f"预览图已保存: {preview_path}")


def sweep_thresholds(path: str, template: str = _TPL_CHALLENGE):
    """参数扫描，找最佳亮度阈值和比例阈值组合。"""
    img = cv2.imread(path)
    if img is None:
        print(f"ERROR: 无法加载 {path}")
        return

    h_img, w_img = img.shape[:2]
    if (w_img, h_img) != (960, 540):
        img = cv2.resize(img, (960, 540))

    if not os.path.exists(template):
        print(f"ERROR: 模板文件不存在: {template}")
        return

    matches = find_all_templates(img, template, threshold=_CHALLENGE_THRESHOLD)
    matches = nms_by_distance(matches)

    if not matches:
        print("未找到标志")
        return

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    print(f"\n找到 {len(matches)} 个标志")
    print(f"\n{'='*80}")
    print("参数扫描: bright_v_threshold × glow_bright_ratio")
    print(f"{'='*80}")

    for v_thr in range(140, 230, 10):
        print(f"\n--- bright_v_threshold = {v_thr} ---")
        for i, m in enumerate(matches):
            cx, cy = m.center
            stats = analyze_marker_glow(hsv, cx, cy, bright_v_thr=v_thr)
            print(f"  标志[{i}] ({cx},{cy}): "
                  f"bright_ratio={stats['bright_ratio']:.3f}, "
                  f"avg_v={stats['avg_v']:.1f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print(f"  python {sys.argv[0]} <screenshot.png>                  # 分析")
        print(f"  python {sys.argv[0]} --crop <screenshot.png> x y w h  # 裁切模板")
        print(f"  python {sys.argv[0]} --sweep <screenshot.png>          # 参数扫描")
        sys.exit(1)

    if sys.argv[1] == "--crop":
        if len(sys.argv) < 7:
            print("用法: --crop <screenshot.png> x y w h")
            sys.exit(1)
        crop_template(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
                      int(sys.argv[5]), int(sys.argv[6]))
    elif sys.argv[1] == "--sweep":
        sweep_thresholds(sys.argv[2])
    else:
        for p in sys.argv[1:]:
            analyze_screenshot(p)
