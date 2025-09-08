# UI 管理器设计（UI Manager）

本设计定义一个可扩展的 UI 管理组件，用于在任务执行前将应用导航到对应的 UI 界面，并在执行过程中提供稳定的 UI 检测与跳转能力。

目标：
- 任务声明所需的 `required_ui`，执行器先调用 UI 管理器完成 UI 就位，再运行任务主逻辑。
- 通过模板匹配（默认阈值 0.85）与像素锚点校验实现稳健的 UI 识别。
- 以 UI 状态图（有向图）描述各 UI 之间的跳转路径与操作序列，支持回退/重置策略。

## 模块结构

位置：`src/app/modules/ui/`

```
ui/
├── manager.py     # UIManager：对外入口，封装检测/跳转/重置
├── detector.py    # UI 检测实现（模板匹配 + 像素锚点）
├── graph.py       # UI 状态图（UIId 节点 + Edge 跳转）
├── registry.py    # UI 定义注册：模板、ROI、阈值、锚点、路由
├── types.py       # UIId/数据结构（UI 定义、检测结果、边定义等）
└── __init__.py
```

依赖：
- `modules.vision.template`: `match_template`/`find_all_templates`
- `modules.vision.utils`: `pixel_match` 等
- `modules.emu.adapter`: `EmulatorAdapter`（capture/tap/swipe）

## 资源组织

建议在 `assets/ui/` 下为每个 UI 建立一套资源：
```
assets/ui/
├── home/
│   ├── title.png        # 主页标题模板
│   ├── anchor_play.png  # 主页上某显著按钮模板
│   └── ui.json          # UI 定义（阈值/ROI/像素锚点等）
├── friends/
│   ├── title.png
│   └── ui.json
└── foster/
    ├── button.png
    └── ui.json
```

ui.json（示例）：
```json
{
  "id": "HOME",
  "threshold": 0.88,
  "templates": [
    {"name": "title", "file": "title.png", "roi": null},
    {"name": "anchor_play", "file": "anchor_play.png", "roi": [100, 50, 400, 200]}
  ],
  "pixels": [
    {"x": 1200, "y": 60, "rgb": [255, 255, 255], "tolerance": 10}
  ]
}
```

## 核心数据结构（types.py）

- `UIId`: `Enum` 或 `Literal[str]`（如 `"HOME" | "FRIENDS" | "FOSTER"`）
- `TemplateDef { name, path, roi?, threshold? }`
- `PixelDef { x, y, rgb|bgr, tolerance }`
- `UIDef { id, templates: [TemplateDef], pixels?: [PixelDef], threshold?: float }`
- `UIDetectResult { ui: UIId|"UNKNOWN", score: float, anchors: dict, matched_templates: [str], debug: dict }`
- `Edge { src: UIId, dst: UIId, actions: [Action], guard?: Guard }`
- `Action`: `{ type: "tap"|"swipe"|"sleep"|"back"|"home"|"tap_anchor", args: {...}}`
- `Guard`: 函数或描述，在触发前校验（如资源充足等）

## UI 检测（detector.py）

流程：
1. 获取截图（若未传入）。
2. 对候选 UI（注册顺序或分组优先级）执行模板匹配：
   - 阈值：使用 `UI_DEF.threshold`，未设置则默认 0.85。
   - ROI：若模板定义了 ROI，则对 ROI 区域裁剪后匹配。
   - 评分：可取匹配模板中的最高分，或多模板得分汇总（如平均/加权）。
3. 如模板达到阈值，再进行像素锚点校验（允许容差）。
4. 产出 `UIDetectResult`（包含 matched_templates、anchors 如按钮中心点 等）。
5. 未命中则返回 `UNKNOWN`。

扩展：
- 支持 UI 白名单/黑名单先验，减少尝试数量（基于上一次 UI）。
- 提供 `fast_mode`：先粗匹配，必要时二次精匹配。

## UI 路由图（graph.py）

定义 UI 状态与跳转边，类似有限状态机：
```
HOME --tap(friends_tab)--> FRIENDS --tap(foster_entry)--> FOSTER
```

边上动作序列（Actions）支持：
- `tap(x,y)`、`tap_anchor(name)`（使用 detector 暴露的锚点中心）
- `swipe(x1,y1,x2,y2,dur_ms)`
- `sleep(ms)` 等待 UI 渲染
- `back`/`home`（需要 `Adb` 增加按键能力，或通过模板定位“返回”按钮点击）

执行策略：
- 每个动作后进行一次短等待和 UI 重新检测；若到达目标则提前结束。
- 边可配置最大重试次数；失败则回退到上一步或尝试备用边。

## UI 管理器（manager.py）

接口：
```python
class UIManager:
    def __init__(self, adapter: EmulatorAdapter, capture_method: str = 'adb', *, ui_config: dict | None = None): ...

    def detect_ui(self, image: bytes | None = None) -> UIDetectResult: ...

    def ensure_ui(
        self,
        target: UIId,
        *,
        max_steps: int = 8,
        step_timeout: float = 3.0,
        threshold: float | None = None,
    ) -> bool: ...

    def navigate(self, source: UIId, target: UIId) -> bool: ...
```

实现要点：
- `capture_method` 默认 `'adb'`，可切换 `'ipc'`。
- `ensure_ui` 主循环：
  1) 检测当前 UI；命中目标立即返回。
  2) 若未知 UI：尝试 `back` 若干次或调用“重置到主页”的路径；否则失败退出。
  3) 根据路由图选择一条从当前 UI 到目标的边，按序执行动作，每步后校验。
  4) 超过 `max_steps` 或 `step_timeout` 则抛 `UINavigateTimeout`。
- 记录日志：每步操作（tap/swipe/back）、检测得分、截图时间开销。
- 可选：缓存最近 UI 以优化下次检测。

## 与执行器的集成

1. 任务对象声明 `required_ui: UIId`（或在执行器中静态映射 TaskType→UIId）。
2. 执行器在 `prepare()` 阶段：
   - 启动/唤醒应用（`adapter.start_app(...)`）。
   - `UIManager.ensure_ui(required_ui)`；失败则返回准备失败并记录错误。
3. `execute()` 阶段中，如 UI 漂移，可按需调用 `ensure_ui` 进行纠正。

## 配置与阈值

默认阈值 0.85；可在：
- 全局 `UI_CONFIG.default_threshold`
- 每个 UI 的 `ui.json.threshold`
- `ensure_ui(..., threshold=...)` 覆盖

像素锚点匹配：
- 使用 `vision.utils.pixel_match`，支持每通道容差，默认 RGB 颜色。
- 常用于高相似度或小型控件的二次确认。

## 错误与恢复

- `UIUnknownError`：连续多次无法识别当前 UI。
- `UINavigateTimeout`：跳转超时或到达步数上限。
- 恢复策略：
  - BACK 链：连续按返回数次直至主页
  - HOME 重置：若支持从通知栏或系统级返回主页（需设备支持）
  - 重新启动应用：`adapter.stop_app()` → `start_app()`

## 示例路线（以 Foster 为例）

目标 UI：`FOSTER`。

候选路线：
1. `HOME --tap(friends_tab)--> FRIENDS --tap(foster_entry)--> FOSTER`
2. 回退路径：`UNKNOWN --back--> ? --back--> HOME`（循环尝试）

动作参数由 `registry` 中的 UI 模板锚点提供，如 `friends_tab`、`foster_entry` 的中心坐标。

## 测试建议

- 单测：
  - 给定不同截图，`detector.detect` 返回 UI 及置信度。
  - `graph` 的边执行后，到达预期 UI（通过 mock 截图）。
  - 容错：阈值边界、像素容差、未知 UI 回退。
- 集成：
  - 以 `MockAdapter` 模拟截图序列与点击副作用，验证 `ensure_ui` 路径选择与超时处理。

