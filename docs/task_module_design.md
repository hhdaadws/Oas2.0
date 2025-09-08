# 统一任务模块设计（Scripted Task Runner）

目标：为长线任务提供一致、可维护的执行框架。每个任务在执行前由 UI 管理器先就位（跳转到目标 UI），再按脚本化步骤完成一系列“截图→匹配→操作→校验”的循环，支持分支、重试与超时。

## 设计原则
- 单一职责：UI 就位交给 UIManager；任务逻辑只关心当前 UI 下的操作步骤。
- 可脚本化：任务由一组 Step 描述，便于复用、测试与维护。
- 鲁棒性：每步均可配置阈值（默认 0.85）、重试与等待；异常有回退与恢复策略。
- 可观测：每步日志与可选截图留存；统计耗时与命中率。

## 模块关系
- EmulatorAdapter：提供截图（ADB/IPC）、点击、滑动与应用启动。
- UIManager（见 ui_manager_design.md）：`ensure_ui(required_ui)` 负责任务入口就位。
- Vision：模板匹配与像素匹配（默认阈值 0.85）。
- TaskRunner：读取 TaskSpec，按 Step 顺序执行，管理循环、分支、重试与超时。

## 数据模型（建议）
- TaskSpec
  - `id: str`（或绑定到 `TaskType`）
  - `required_ui: str`（任务入口 UI 标识）
  - `steps: List[StepSpec]`
  - `timeout: float?`（全局超时）
- StepSpec（核心）
  - `type: OpType`（见下）
  - `template?: TemplateSpec`（用于模板相关步骤）
  - `roi?: (x,y,w,h)`（可选，缩小匹配范围）
  - `threshold?: float`（默认 0.85）
  - `click_offset?: (dx,dy)`（点击偏移）
  - `expect?: {present|absent}`（等待/断言模板是否存在）
  - `retries?: int`，`interval?: float`，`step_timeout?: float`
  - `next?: {on_success: label, on_fail: label}`（分支）
  - `label?: str`（用于跳转）
- 模板与像素
  - `TemplateSpec { path_or_bytes, threshold?, roi? }`
  - `PixelSpec { x, y, rgb, tolerance }`
- OpType（操作类型）
  - `ensure_ui`：确保处于某 UI（委托给 UIManager）
  - `tap_template`：匹配模板并点击（含重试）
  - `wait_template`：等待模板出现/消失
  - `tap`：按绝对坐标点击
  - `swipe`：滑动
  - `sleep`：等待
  - `branch`：按条件（模板/像素）跳转到不同 label

注：项目中已有初步类型草案：`src/app/modules/executor/task_types.py`（TemplateSpec/PixelSpec/StepResult/OpType）。

## 执行语义
- 全局流程
  1) `prepare`：启动应用（如需）→ `UIManager.ensure_ui(spec.required_ui)`
  2) `run`：按 steps 顺序执行，维护当前 `pc`（程序计数器/label），直到自然结束或超时/失败
  3) `cleanup`：必要时回到稳定 UI、释放资源
- 核心步骤
  - `tap_template`
    - 循环：截图 → 在 ROI 内 `match_template` → 命中则点击 `match.center + offset` → 成功
    - 未命中：等待 `interval` 后重试，直到 `retries/step_timeout`
  - `wait_template`
    - 截图→匹配：根据 `expect` 为 present/absent 判定；不满足则重试
  - `branch`
    - 按模板/像素判定，跳转 `next.on_success/on_fail`
  - `ensure_ui`
    - 调 `UIManager.ensure_ui(target)`；失败视为步骤失败

## 失败与恢复
- Step 失败：
  - 若定义了 `next.on_fail` 则跳转继续；否则抛出并由 TaskRunner 统一处理
- Runner 恢复：
  - 记录上下文并尝试 `UIManager.ensure_ui(required_ui)` 二次校正
  - 仍失败：可尝试 BACK 链/重启应用（由上层策略决定）

## 观察性与调试
- Step 级日志：开始/结果/耗时/score/重试次数
- 可选保留关键截图（命中/未命中）与匹配热力图（阈值下发）
- 统计：每模板命中率、平均点击耗时

## 配置约定
- 未提供阈值统一使用 `0.85`
- 默认 `retries=5`，`interval=0.5s`，`step_timeout=5s`
- ROI 以大图左上角为原点（像素坐标）

## 示例（寄养任务：FOSTER）
- required_ui: `HOME`
- steps:
  1) `tap_template`: 打开“好友/寮”入口
  2) `wait_template`: 等待“好友界面”标题出现（切换 UI）
  3) `tap_template`: 点击“寄养”入口
  4) `wait_template`: 等待“寄养列表”出现
  5) `tap_template`: 点击“寄养确认/一键寄养”按钮
  6) `wait_template`: 等待结果弹窗出现→消失（完成）

## 与现有代码的集成点
- RealExecutor（待实现）
  - `prepare`：调用 `UIManager.ensure_ui(required_ui)`
  - `execute`：构造 `TaskRunner(spec).run(context)` 返回产出（状态/指标）
  - `cleanup`：按需回到 HOME 或无操作
- 资源
  - 模板文件位于 `assets/templates/` 或 `assets/ui/<ui>/...`
  - 通过 `TemplateSpec.path_or_bytes` 支持打包二进制模板

## 模块草图
- `src/app/modules/executor/script/definition.py`
  - `TaskSpec/StepSpec/ConditionSpec`（dataclasses）
- `src/app/modules/executor/script/runner.py`
  - `TaskRunner`：`run(context)`；内部 `pc/labels`、截图缓存、重试器
- `src/app/modules/executor/script/ops.py`
  - 具体 step 执行器：`run_tap_template`/`run_wait_template` 等
- `src/app/modules/executor/script/errors.py`
  - `StepTimeout/TemplateNotFound/UINavigateTimeout` 等

## 实施顺序（建议）
1) 定义 TaskSpec/StepSpec 与基础 Runner（仅 `tap_template`/`wait_template`）
2) 接入 UIManager.ensure_ui；实现基础恢复策略
3) 增加 `branch`/`tap`/`swipe` 与像素断言
4) 增加指标与工件导出；补充单测与 mock 适配器

以上设计满足“先 UI 就位、再按模板匹配驱动长流程”的诉求，同时保持任务脚本化、可扩展与可维护。

