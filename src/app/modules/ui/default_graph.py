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

    # 委派 -> 探索：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="WEIPAI",
            dst="TANSUO",
            actions=[Action(type="tap_anchor", args=("back",)), Action(type="sleep", args=(800,))],
        )
    )

    # 庭院 -> 商店：点击 shangdian 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="SHANGDIAN",
            actions=[
                Action(type="tap_anchor", args=("shangdian", 921, 490, 3, 2500)),
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

    # 探索 -> 地鬼：点击 digui 锚点
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="DIGUI",
            actions=[
                Action(type="tap_anchor", args=("digui",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 地鬼 -> 探索：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="DIGUI",
            dst="TANSUO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 探索 -> 秘闻：点击 miwen 锚点
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="MIWEN",
            actions=[
                Action(type="tap_anchor", args=("miwen",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 秘闻 -> 探索：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="MIWEN",
            dst="TANSUO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 庭院 -> 寮界面：点击 liao 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="LIAO",
            actions=[
                Action(type="tap_anchor", args=("liao", 921, 490, 3, 2500)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮界面 -> 寮信息：点击寮消息
    graph.add_edge(
        Edge(
            src="LIAO",
            dst="LIAO_XINXI",
            actions=[
                Action(type="tap_anchor", args=("liaoxinxi",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮信息 -> 寮活动：点击神社
    graph.add_edge(
        Edge(
            src="LIAO_XINXI",
            dst="LIAO_HUODONG",
            actions=[
                Action(type="tap_anchor", args=("shenshe",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮信息 -> 寮界面：点击 xinxi 返回
    graph.add_edge(
        Edge(
            src="LIAO_XINXI",
            dst="LIAO",
            actions=[
                Action(type="tap_anchor", args=("xinxi",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮活动 -> 寮商店：点击功勋商店
    graph.add_edge(
        Edge(
            src="LIAO_HUODONG",
            dst="LIAO_SHANGDIAN",
            actions=[
                Action(type="tap_anchor", args=("gongxunshangdian",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮商店 -> 寮活动：点击 exit.png 返回
    graph.add_edge(
        Edge(
            src="LIAO_SHANGDIAN",
            dst="LIAO_HUODONG",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮活动 -> 寮界面：点击 back.png 返回
    graph.add_edge(
        Edge(
            src="LIAO_HUODONG",
            dst="LIAO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 寮界面 -> 庭院：点击 back.png 返回
    graph.add_edge(
        Edge(
            src="LIAO",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 邮箱：点击 youjian 图标
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="YOUXIANG",
            actions=[
                Action(type="tap_anchor", args=("youjian",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 邮箱 -> 庭院：点击 exit 返回
    graph.add_edge(
        Edge(
            src="YOUXIANG",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 式神：点击 shishen 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="SHISHEN",
            actions=[
                Action(type="tap_anchor", args=("shishen", 921, 490, 3, 2500)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 式神 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="SHISHEN",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 召唤：点击 zhaohuan 锚点
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="ZHAOHUAN",
            actions=[
                Action(type="tap_anchor", args=("zhaohuan",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 召唤 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="ZHAOHUAN",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 好友：点击 haoyou 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="HAOYOU",
            actions=[
                Action(type="tap_anchor", args=("haoyou", 921, 490, 3, 2500)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 好友 -> 庭院：点击 exit 返回
    graph.add_edge(
        Edge(
            src="HAOYOU",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 悬赏：点击 xuanshang 锚点
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="XUANSHANG",
            actions=[
                Action(type="tap_anchor", args=("xuanshang",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 悬赏 -> 庭院：点击 exit 返回
    graph.add_edge(
        Edge(
            src="XUANSHANG",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    # 庭院 -> 新手任务：点击 xinshou 锚点
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="XINSHOU",
            actions=[
                Action(type="tap_anchor", args=("xinshou",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 新手任务 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="XINSHOU",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(2000,)),
            ],
        )
    )

    return graph


__all__ = ["build_default_graph"]

