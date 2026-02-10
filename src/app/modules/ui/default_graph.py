from __future__ import annotations

from .graph import Action, Edge, UIGraph


def build_default_graph() -> UIGraph:
    """构建默认 UI 跳转图。"""
    graph = UIGraph()

    # 庭院 -> 探索：点击 tansuo_x 系列按钮
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="TANSUO",
            actions=[Action(type="tap_anchor", args=("tansuo",)), Action(type="sleep", args=(800,))],
        )
    )

    # 探索 -> 委派：点击 weipai
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="WEIPAI",
            actions=[Action(type="tap_anchor", args=("weipai",)), Action(type="sleep", args=(800,))],
        )
    )

    # 庭院 -> 商店：先展开菜单（如果 haoyou 未出现），然后点击 shangdian
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="SHANGDIAN",
            actions=[
                Action(type="tap", args=(921, 490)),
                Action(type="sleep", args=(3000,)),
                Action(type="re_detect"),
                Action(type="tap_anchor", args=("shangdian",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 商店 -> 庭院：点击返回按钮（back.png），等待 jiacheng.png 出现确认到达庭院
    graph.add_edge(
        Edge(
            src="SHANGDIAN",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 探索 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    return graph


__all__ = ["build_default_graph"]

