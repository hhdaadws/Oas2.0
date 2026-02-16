"""验证 detect_tupo_grid 对 tupo.png 的检测结果"""
import sys
sys.path.insert(0, "src")

from app.modules.vision.tupo_detect import detect_tupo_grid, find_best_target


def verify(path: str):
    print(f"检测: {path}")
    print("=" * 60)

    result = detect_tupo_grid(path)

    for card in result.cards:
        status_cn = {
            "defeated": "已击败",
            "failed": "没打过",
            "not_challenged": "未挑战",
        }[card.state.value]

        print(
            f"  卡片[{card.index}] row={card.row} col={card.col}: "
            f"{status_cn:6s}  "
            f"avg_v={card.avg_v:5.1f}  "
            f"failed_score={card.failed_score:.3f}  "
            f"center={card.center}"
        )

    print(f"\n统计: 已击败={result.defeated_count}, "
          f"没打过={result.failed_count}, "
          f"未挑战={result.not_challenged_count}")
    print(f"全部击败: {result.all_defeated}")

    target = find_best_target(path)
    if target:
        print(f"推荐目标: 卡片[{target.index}] center={target.center}")
    else:
        print("推荐目标: 无（全部已击败）")

    # 预期结果验证
    expected = {
        0: "defeated",      # 第1排第1个 - 已击败
        1: "failed",        # 第1排第2个 - 没打过
        3: "defeated",      # 第2排第1个 - 已击败
    }
    # 其余为 not_challenged

    print("\n预期验证:")
    all_ok = True
    for card in result.cards:
        exp = expected.get(card.index, "not_challenged")
        ok = card.state.value == exp
        mark = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
            status_cn = {"defeated": "已击败", "failed": "没打过", "not_challenged": "未挑战"}
            print(f"  [{mark}] 卡片[{card.index}]: 预期={status_cn[exp]}, 实际={status_cn[card.state.value]}")

    if all_ok:
        print("  全部通过!")
    else:
        print("  存在不匹配项")


if __name__ == "__main__":
    verify(sys.argv[1] if len(sys.argv) > 1 else "tupo.png")
