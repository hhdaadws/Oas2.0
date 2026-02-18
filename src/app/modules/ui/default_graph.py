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
                Action(type="tap_anchor", args=("shangdian", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 探索 -> 结界突破：点击 jiejietupo 锚点
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="JIEJIE_TUPO",
            actions=[
                Action(type="tap_anchor", args=("jiejietupo",)),
                Action(type="sleep", args=(1500,)),
            ],
        )
    )

    # 结界突破 -> 探索：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="JIEJIE_TUPO",
            dst="TANSUO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 寮界面：点击 liao 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="LIAO",
            actions=[
                Action(type="tap_anchor", args=("liao", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 寮 -> 结界：点击 jiejie 锚点
    graph.add_edge(
        Edge(
            src="LIAO",
            dst="JIEJIE",
            actions=[
                Action(type="tap_anchor", args=("jiejie",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 结界 -> 寮：点击 back 返回
    graph.add_edge(
        Edge(
            src="JIEJIE",
            dst="LIAO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 结界 -> 结界养成：点击 (462, 258) 进入
    graph.add_edge(
        Edge(
            src="JIEJIE",
            dst="JIEJIE_YANGCHENG",
            actions=[
                Action(type="tap", args=(462, 258)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 结界养成 -> 结界：点击 exit_dark 返回
    graph.add_edge(
        Edge(
            src="JIEJIE_YANGCHENG",
            dst="JIEJIE",
            actions=[
                Action(type="tap_anchor", args=("exit_dark",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 结界 -> 饭盒：点击区域 (615,405)-(716,425) 的中心坐标
    graph.add_edge(
        Edge(
            src="JIEJIE",
            dst="FANHE",
            actions=[
                Action(type="tap", args=(665, 415)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 饭盒 -> 结界：点击 exit 返回
    graph.add_edge(
        Edge(
            src="FANHE",
            dst="JIEJIE",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 饭盒 -> 酒壶：点击 to_jiuhu 切换
    graph.add_edge(
        Edge(
            src="FANHE",
            dst="JIUHU",
            actions=[
                Action(type="tap_anchor", args=("to_jiuhu",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 酒壶 -> 饭盒：点击 to_fanhe 切换
    graph.add_edge(
        Edge(
            src="JIUHU",
            dst="FANHE",
            actions=[
                Action(type="tap_anchor", args=("to_fanhe",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 酒壶 -> 结界：点击 exit 返回
    graph.add_edge(
        Edge(
            src="JIUHU",
            dst="JIEJIE",
            actions=[
                Action(type="tap_anchor", args=("exit",)),
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 式神：点击 shishen 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="SHISHEN",
            actions=[
                Action(type="tap_anchor", args=("shishen", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 召唤 -> 召唤礼包：点击 zhaohuan_shangdian 锚点
    graph.add_edge(
        Edge(
            src="ZHAOHUAN",
            dst="ZHAOHUAN_LIBAO",
            actions=[
                Action(type="tap_anchor", args=("zhaohuan_shangdian",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 召唤礼包 -> 召唤：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="ZHAOHUAN_LIBAO",
            dst="ZHAOHUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 好友：点击 haoyou 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="HAOYOU",
            actions=[
                Action(type="tap_anchor", args=("haoyou", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(1200,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
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
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 组队：点击 zudui 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="ZUDUI",
            actions=[
                Action(type="tap_anchor", args=("zudui", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 组队 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="ZUDUI",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 签到：点击 qiandao 锚点
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="QIANDAO",
            actions=[
                Action(type="tap_anchor", args=("qiandao",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 签到 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="QIANDAO",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 探索 -> 副本：点击 yuhun 锚点（探索界面上的御魂入口按钮）
    graph.add_edge(
        Edge(
            src="TANSUO",
            dst="FUBEN",
            actions=[
                Action(type="tap_anchor", args=("yuhun",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 副本 -> 探索：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="FUBEN",
            dst="TANSUO",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 副本 -> 御魂：点击 fuben 锚点
    graph.add_edge(
        Edge(
            src="FUBEN",
            dst="YUHUN",
            actions=[
                Action(type="tap_anchor", args=("fuben",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 御魂 -> 副本：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="YUHUN",
            dst="FUBEN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 花合战：点击 huahezhan 锚点（在庭院右侧边栏）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="HUAHEZHAN",
            actions=[
                Action(type="tap_anchor", args=("huahezhan", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 花合战 -> 庭院：点击返回按钮（back_huahezhan.png）
    graph.add_edge(
        Edge(
            src="HUAHEZHAN",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back_huahezhan",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 花合战 -> 成就：点击 chengjiu 锚点
    graph.add_edge(
        Edge(
            src="HUAHEZHAN",
            dst="CHENGJIU",
            actions=[
                Action(type="tap_anchor", args=("chengjiu",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 成就 -> 花合战：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="CHENGJIU",
            dst="HUAHEZHAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 图鉴：点击 tujian 锚点（未出现则点击 921,490 展开侧边栏后重试）
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="TUJIAN",
            actions=[
                Action(type="tap_anchor", args=("tujian", 921, 490, 3, 1500)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 图鉴 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="TUJIAN",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    # 庭院 -> 对弈竞猜：点击 dy_rukou 锚点
    graph.add_edge(
        Edge(
            src="TINGYUAN",
            dst="DUIYI_JINGCAI",
            actions=[
                Action(type="tap_anchor", args=("dy_rukou",)),
                Action(type="sleep", args=(1200,)),
            ],
        )
    )

    # 对弈竞猜 -> 庭院：点击返回按钮（back.png）
    graph.add_edge(
        Edge(
            src="DUIYI_JINGCAI",
            dst="TINGYUAN",
            actions=[
                Action(type="tap_anchor", args=("back",)),
                Action(type="sleep", args=(800,)),
            ],
        )
    )

    return graph


__all__ = ["build_default_graph"]
