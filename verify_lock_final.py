"""验证 detect_jiekai_lock 检测函数"""
import sys
sys.path.insert(0, "src")

from app.modules.vision.color_detect import detect_jiekai_lock

print("=== 结界突破锁定检测验证 ===\n")

# 测试锁定状态
result_lock = detect_jiekai_lock("lock.png")
print(f"lock.png:   locked={result_lock.locked}, score={result_lock.score:.4f}, center={result_lock.center}")
assert result_lock.locked, "lock.png 应该检测为锁定状态!"

# 测试未锁定状态
result_unlock = detect_jiekai_lock("unlock.png")
print(f"unlock.png: locked={result_unlock.locked}, score={result_unlock.score:.4f}, center={result_unlock.center}")
assert not result_unlock.locked, "unlock.png 应该检测为未锁定状态!"

print(f"\n得分差距: {result_lock.score - result_unlock.score:.4f}")
print("\n全部通过!")
