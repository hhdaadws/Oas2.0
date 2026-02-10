# 新增任务类型指南

本文档说明如何在系统中添加一个新的任务类型，涵盖后端常量、调度、执行器、API 以及前端 UI 的完整链路。

## 涉及文件一览

| 序号 | 文件 | 说明 |
|------|------|------|
| 1 | `src/app/core/constants.py` | 任务枚举、优先级、默认配置 |
| 2 | `src/app/modules/tasks/feeder.py` | 调度扫描，判断任务是否就绪 |
| 3 | `src/app/modules/executor/worker.py` | 根据任务类型创建执行器 + next_time 更新 |
| 4 | `src/app/modules/executor/` | 新建具体执行器文件（若非占位） |
| 5 | `src/app/modules/web/routers/accounts.py` | TaskConfigUpdate Pydantic 模型 |
| 6 | `frontend/src/views/Accounts.vue` | 前端任务配置 UI |

## 第 1 步：定义任务常量

**文件：** `src/app/core/constants.py`

### 1.1 添加枚举值

```python
class TaskType(str, Enum):
    # ... 现有任务 ...
    MY_NEW_TASK = "新任务名"   # 添加这行
    REST = "休息"              # REST 始终保持在最后
```

枚举的 `value` 是中文名，必须与 `DEFAULT_TASK_CONFIG` 中的 key 一致。

### 1.2 设置优先级

```python
TASK_PRIORITY = {
    # 数值越大优先级越高，同一批次内按此排序
    TaskType.MY_NEW_TASK: 45,   # 根据业务需要插入合适位置
}
```

现有优先级参考：

| 优先级 | 任务 |
|--------|------|
| 100 | 起号 |
| 90 | 加好友 |
| 80 | 勾协 |
| 70 | 委托 |
| 65 | 弥助 |
| 60 | 寄养 |
| 55 | 领取登录礼包 |
| 50 | 探索突破 |
| 48 | 逢魔 |
| 46 | 地鬼 |
| 45 | 领取邮件 |
| 44 | 道馆 |
| 40 | 结界卡合成 |
| 35 | 爬塔 |
| 20 | 休息 |

### 1.3 添加默认配置

```python
DEFAULT_TASK_CONFIG = {
    # 时间触发型（大多数任务）
    "新任务名": {
        "enabled": True,
        "next_time": "2020-01-01 00:00"   # 默认过去时间，首次扫描即触发
    },

    # 条件触发型（如探索突破按体力触发）
    # "新任务名": {
    #     "enabled": True,
    #     "stamina_threshold": 1000
    # },
}
```

`"2020-01-01 00:00"` 是惯例默认值，因为它是过去时间，Feeder 首次扫描时 `is_time_reached()` 返回 True，使任务立即就绪。

## 第 2 步：调度触发

**文件：** `src/app/modules/tasks/feeder.py`

在 `_collect_ready_tasks()` 方法中添加触发检查。

### 时间触发型（最常见）

```python
def _collect_ready_tasks(self, account, cfg):
    intents = []
    # ... 现有检查 ...
    self._check_time_task(intents, account, cfg, "新任务名", TaskType.MY_NEW_TASK)
```

`_check_time_task` 自动检查 `enabled` 是否为 True、`next_time` 是否已到达。

### 条件触发型

```python
my_task = cfg.get("新任务名", {})
if my_task.get("enabled") is True and account.stamina >= my_task.get("stamina_threshold", 1000):
    intents.append(TaskIntent(account_id=account.id, task_type=TaskType.MY_NEW_TASK))
```

## 第 3 步：执行器

**文件：** `src/app/modules/executor/worker.py`

### 3.1 占位任务

无需修改。未匹配到的任务类型自动走 `else` 分支使用 `MockExecutor`（立即返回成功）。

### 3.2 正式执行器

新建 `src/app/modules/executor/my_new_task.py`：

```python
from .base import BaseExecutor
from ...core.constants import TaskStatus

class MyNewTaskExecutor(BaseExecutor):
    async def prepare(self):
        # 可通过 self.shared_adapter 复用批次内的模拟器连接
        pass

    async def execute(self):
        return {"status": TaskStatus.SUCCEEDED}

    async def cleanup(self):
        # 批次中非最后一个任务会跳过 cleanup
        pass
```

在 `worker.py` 的 `_run_intent()` 中添加分支：

```python
elif intent.task_type == TaskType.MY_NEW_TASK:
    from .my_new_task import MyNewTaskExecutor
    executor = MyNewTaskExecutor(
        worker_id=self.emulator.id,
        emulator_id=self.emulator.id,
        emulator_row=self.emulator,
        system_config=self.syscfg,
    )
```

### 3.3 配置 next_time 更新逻辑

在 `worker.py` 的 `_compute_next_time()` 中添加。常见模式：

| 模式 | 示例 | 适用任务 |
|------|------|----------|
| 明天 00:01 | `f"{tomorrow} 00:01"` | 加好友、领取邮件、爬塔、逢魔、地鬼、道馆 |
| 固定时间点 | `get_next_fixed_time(["12:00","18:00"])` | 委托 |
| 固定间隔 | `now + timedelta(hours=6)` | 寄养 |
| 自定义 | 在执行器内覆写 `_update_next_time()` | 弥助、领取登录礼包 |

```python
# 每日任务
if task_type in (TaskType.MY_NEW_TASK,):
    tomorrow = now_beijing().date() + timedelta(days=1)
    return f"{tomorrow.isoformat()} 00:01"
```

### 3.4 自定义 next_time（可选）

将任务类型加入 `_EXECUTOR_HAS_OWN_UPDATE` 集合，然后在执行器中实现 `_update_next_time()`。

## 第 4 步：后端 API 模型

**文件：** `src/app/modules/web/routers/accounts.py`

```python
class TaskConfigUpdate(BaseModel):
    # ... 现有字段 ...
    my_new_task: Optional[Dict[str, Any]] = Field(default=None, alias="新任务名")
    signin: Optional[Dict[str, Any]] = Field(default=None, alias="签到")  # 签到始终在最后
```

`alias` 必须与 `DEFAULT_TASK_CONFIG` 中的中文 key 完全一致。

## 第 5 步：前端 UI

**文件：** `frontend/src/views/Accounts.vue`，需要修改 4 处。

### 5.1 template - 任务配置表单（签到之前插入）

```html
<el-form-item label="新任务名">
  <el-switch v-model="taskConfig.新任务名.enabled" @change="updateTaskConfigData" />
  <el-date-picker
    v-if="taskConfig.新任务名.enabled"
    v-model="taskConfig.新任务名.next_time"
    type="datetime" placeholder="下次执行时间"
    format="YYYY-MM-DD HH:mm" value-format="YYYY-MM-DD HH:mm"
    style="margin-left: 10px; width: 200px"
    @change="updateTaskConfigData"
  />
</el-form-item>
```

### 5.2 script - taskConfig 默认值

```javascript
const taskConfig = reactive({
  // ... 现有任务 ...
  新任务名: { enabled: true, next_time: "2020-01-01 00:00" },
  签到: { enabled: false, status: '未签到', signed_date: null }
})
```

### 5.3 script - handleNodeClick 加载逻辑

```javascript
taskConfig.新任务名 = {
  enabled: savedConfig.新任务名?.enabled === true,
  next_time: savedConfig.新任务名?.next_time ?? "2020-01-01 00:00"
}
```

### 5.4 script - updateTaskConfigData 发送数据

```javascript
const configToSend = {
  // ... 现有任务 ...
  "新任务名": {
    enabled: taskConfig["新任务名"].enabled,
    next_time: taskConfig["新任务名"].next_time
  },
}
```

## 完整检查清单

- [ ] `constants.py` - `TaskType` 枚举
- [ ] `constants.py` - `TASK_PRIORITY` 优先级
- [ ] `constants.py` - `DEFAULT_TASK_CONFIG` 默认配置
- [ ] `feeder.py` - `_collect_ready_tasks()` 触发检查
- [ ] `worker.py` - `_run_intent()` 执行器分支（占位可跳过）
- [ ] `worker.py` - `_compute_next_time()` 时间更新逻辑
- [ ] `accounts.py` - `TaskConfigUpdate` Pydantic 模型字段
- [ ] `Accounts.vue` template - `<el-form-item>` 配置 UI
- [ ] `Accounts.vue` script - `taskConfig` reactive 默认值
- [ ] `Accounts.vue` script - `handleNodeClick` 加载逻辑
- [ ] `Accounts.vue` script - `configToSend` 发送数据

## 阵容分组配置（可选）

如果新任务需要支持阵容配置，额外修改 3 处：

**1. `src/app/modules/lineup/__init__.py`**

```python
LINEUP_SUPPORTED_TASKS = ["逢魔", "地鬼", "探索", "结界突破", "道馆", "新任务名"]
```

**2. `src/app/modules/web/routers/accounts.py`**

```python
class LineupConfigUpdate(BaseModel):
    新任务名: Optional[Dict[str, int]] = None   # {"group": 1, "position": 1}
```

**3. `frontend/src/views/Accounts.vue`**

```javascript
const LINEUP_TASKS = ['逢魔', '地鬼', '探索', '结界突破', '道馆', '新任务名']
```

在执行器中读取阵容配置：

```python
from ...modules.lineup import get_lineup_for_task

lineup = get_lineup_for_task(account.lineup_config or {}, "新任务名")
group = lineup["group"]       # 分组编号 1-7
position = lineup["position"] # 阵容编号 1-7
```

## 任务系统架构简图

```
Feeder (每10秒扫描)
  |
  +- _collect_ready_tasks()    判断哪些任务就绪
  |     +- _check_time_task()  时间触发检查
  |     +- 自定义条件检查       条件触发检查
  |
  +- enqueue_batch()           将就绪任务打包入队
        |
        v
ExecutorService (分发循环)
  |
  +- _dispatcher_loop()        将批次分配给空闲 Worker
        |
        v
WorkerActor (每模拟器一个)
  |
  +- _run_intent()             根据 task_type 创建执行器
  |     +- prepare()
  |     +- execute()
  |     +- cleanup()
  |
  +- _update_next_time()       更新 task_config 中的 next_time
```
