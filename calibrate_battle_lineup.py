"""校准验证 - 用 zhandou.png 验证 battle_lineup_detect 的检测结果"""
import cv2
import sys
sys.path.insert(0, "src")

from app.modules.vision.battle_lineup_detect import (
    detect_battle_groups,
    detect_battle_lineups,
)

img = cv2.imread("zhandou.png")
if img is None:
    print("ERROR: zhandou.png not found")
    sys.exit(1)

h, w = img.shape[:2]
print(f"Image size: {w}x{h}")

# ── 检测分组 ──
groups = detect_battle_groups(img)
print(f"\n=== Groups detected: {len(groups)} ===")
for g in groups:
    print(f"  G{g.index}: top={g.top}, bottom={g.bottom}, center={g.center}, height={g.height}")

# ── 检测阵容 ──
lineups = detect_battle_lineups(img)
print(f"\n=== Lineups detected: {len(lineups)} ===")
for l in lineups:
    print(f"  L{l.index}: top={l.top}, bottom={l.bottom}, center={l.center}, height={l.height}")

# ── 绘制调试图 ──
debug = img.copy()

# 绘制分组格子 (绿色)
for g in groups:
    x1, x2 = 24, 122
    cv2.rectangle(debug, (x1, g.top), (x2, g.bottom), (0, 255, 0), 2)
    cx, cy = g.center
    cv2.circle(debug, (cx, cy), 5, (0, 255, 0), -1)
    cv2.putText(debug, f"G{g.index}", (x1, g.top - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

# 绘制阵容格子 (蓝色)
for l in lineups:
    x1, x2 = 130, 350
    cv2.rectangle(debug, (x1, l.top), (x2, l.bottom), (255, 100, 0), 2)
    cx, cy = l.center
    cv2.circle(debug, (cx, cy), 5, (255, 100, 0), -1)
    cv2.putText(debug, f"L{l.index}", (x1, l.top - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 1)

cv2.imwrite("zhandou_debug_final.png", debug)
print(f"\nDebug image saved: zhandou_debug_final.png")
