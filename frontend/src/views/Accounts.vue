<template>
  <div class="accounts">
    <!-- 操作栏 -->
    <el-card class="action-bar">
      <el-button @click="showAddGameDialog">
        <el-icon><Plus /></el-icon>
        添加ID账号
      </el-button>
      <el-button @click="fetchAccounts">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-button @click="handleSelectAll">
        {{ isAllSelected ? '取消全选' : '全选' }}
      </el-button>
      <el-button type="danger" plain :disabled="selectedGameIds.length === 0" @click="handleBatchDelete">
        批量删除
      </el-button>
    </el-card>

    <!-- 账号列表 -->
    <el-row :gutter="20">
      <!-- 左侧账号树 -->
      <el-col :span="8">
        <el-card class="account-tree">
          <template #header>
            <div class="tree-header">
              <span>账号列表</span>
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-select
                  v-model="statusFilter"
                  placeholder="状态"
                  clearable
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="正常" :value="1" />
                  <el-option label="失效" :value="2" />
                  <el-option label="藏宝阁" :value="3" />
                </el-select>
                <el-input
                  v-model="searchText"
                  placeholder="搜索 账号ID/备注"
                  clearable
                  size="small"
                  style="max-width: 220px"
                />
              </div>
            </div>
          </template>

          <el-tree
            :data="filteredAccountTree"
            :props="treeProps"
            node-key="id"
            show-checkbox
            ref="accountTreeRef"
            check-on-click-node
            default-expand-all
            @check="handleTreeCheck"
            @check-change="handleTreeCheck"
            @node-click="handleNodeClick"
          >
            <template #default="{ node, data }">
              <span class="tree-node">
                <el-icon>
                  <User />
                </el-icon>
                <span>{{ data.label }}</span>
                <el-tag
                  v-if="data.status"
                  :type="getStatusType(data.status)"
                  size="small"
                  class="status-tag"
                >
                  {{ getStatusText(data.status) }}
                </el-tag>
                <el-tag
                  v-if="data.type === 'game' && data.remark"
                  type="info"
                  size="small"
                  class="remark-tag"
                  :title="data.remark"
                >
                  {{ data.remark.length > 6 ? data.remark.substring(0, 6) + '...' : data.remark }}
                </el-tag>
                <el-popconfirm
                  width="220"
                  confirm-button-text="删除"
                  confirm-button-type="danger"
                  cancel-button-text="取消"
                  title="删除该ID账号？此操作不可恢复"
                  @confirm="() => handleDeleteGame(data.id)"
                >
                  <template #reference>
                    <el-button link type="danger" size="small">删除</el-button>
                  </template>
                </el-popconfirm>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <!-- 右侧详情 -->
      <el-col :span="16">
        <el-card v-if="selectedAccount" class="account-detail">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>账号详情: {{ selectedAccount.login_id }}</span>
              <el-button type="primary" size="small" @click="openLineupDialog">
                配置阵容
              </el-button>
            </div>
          </template>

          <!-- 基础信息 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="账号ID">
              {{ selectedAccount.login_id }}
            </el-descriptions-item>
            <el-descriptions-item label="账号类型">
              <el-select
                v-model="selectedAccount.progress"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option value="init" label="刷卡" />
                <el-option value="ok" label="日常" />
              </el-select>
            </el-descriptions-item>
            <el-descriptions-item label="等级">
              <el-input-number
                v-model="selectedAccount.level"
                :min="1"
                :max="999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="体力">
              <el-input-number
                v-model="selectedAccount.stamina"
                :min="0"
                :max="99999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="勾玉">
              {{ selectedAccount.gouyu || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="蓝票">
              {{ selectedAccount.lanpiao || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="金币">
              {{ selectedAccount.gold || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="功勋">
              {{ selectedAccount.gongxun || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="勋章">
              {{ selectedAccount.xunzhang || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="突破票">
              {{ selectedAccount.tupo_ticket || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-select
                v-model="selectedAccount.status"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option :value="1" label="可执行" />
                <el-option :value="2" label="失效" />
                <el-option :value="3" label="上架藏宝阁" />
              </el-select>
            </el-descriptions-item>
            <el-descriptions-item label="备注" :span="2">
              <el-input
                v-model="selectedAccount.remark"
                placeholder="输入备注信息"
                size="small"
                clearable
                maxlength="500"
                show-word-limit
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
          </el-descriptions>

          <!-- 式神状态（仅刷卡阶段显示） -->
          <template v-if="selectedAccount?.progress === 'init'">
            <el-divider>式神状态</el-divider>
            <el-form label-width="100px">
              <el-form-item label="座敷童子">
                <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px;">
                  <span>御魂:</span>
                  <el-select
                    v-model="shikigamiConfig.座敷童子.yuhun"
                    placeholder="未设置"
                    clearable
                    size="small"
                    style="width: 130px"
                    @change="updateShikigamiData"
                  >
                    <el-option
                      v-for="opt in yuhunOptions"
                      :key="opt"
                      :label="opt"
                      :value="opt"
                    />
                  </el-select>
                  <el-checkbox
                    v-model="shikigamiConfig.座敷童子.awakened"
                    @change="updateShikigamiData"
                  >已觉醒</el-checkbox>
                  <span>星级:</span>
                  <el-input-number
                    v-model="shikigamiConfig.座敷童子.star"
                    :min="1"
                    :max="6"
                    size="small"
                    style="width: 100px"
                    @change="updateShikigamiData"
                  />
                  <span>技能等级:</span>
                  <el-input-number
                    v-model="shikigamiConfig.座敷童子.skill_level"
                    :min="1"
                    :max="20"
                    size="small"
                    style="width: 100px"
                    @change="updateShikigamiData"
                  />
                </div>
              </el-form-item>
              <el-form-item label="租借式神" v-if="shikigamiConfig.租借式神 && shikigamiConfig.租借式神.length > 0">
                <el-tag v-for="item in shikigamiConfig.租借式神" :key="typeof item === 'string' ? item : item.name" style="margin-right: 6px;">
                  <template v-if="typeof item === 'string'">{{ item }}</template>
                  <template v-else>{{ item.name }} {{ item.star }}★</template>
                </el-tag>
              </el-form-item>
            </el-form>
          </template>

          <!-- 任务配置 -->
          <el-divider>任务配置</el-divider>
          <el-form label-width="100px">
            <!-- === 起号专属任务（仅 init 状态显示）=== -->
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="领取奖励">
              <el-switch
                v-model="taskConfig.起号_领取奖励.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_领取奖励.enabled"
                v-model="taskConfig.起号_领取奖励.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_领取奖励.enabled"
                v-model="taskConfig.起号_领取奖励.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_领取奖励.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="租借式神">
              <el-switch
                v-model="taskConfig.起号_租借式神.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_租借式神.enabled"
                v-model="taskConfig.起号_租借式神.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_租借式神.enabled"
                v-model="taskConfig.起号_租借式神.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_租借式神.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="新手任务">
              <el-switch
                v-model="taskConfig.起号_新手任务.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_新手任务.enabled"
                v-model="taskConfig.起号_新手任务.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_新手任务.enabled"
                v-model="taskConfig.起号_新手任务.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_新手任务.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="经验副本">
              <el-switch
                v-model="taskConfig.起号_经验副本.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_经验副本.enabled"
                v-model="taskConfig.起号_经验副本.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_经验副本.enabled"
                v-model="taskConfig.起号_经验副本.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_经验副本.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="领取锦囊">
              <el-switch
                v-model="taskConfig.起号_领取锦囊.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_领取锦囊.enabled"
                v-model="taskConfig.起号_领取锦囊.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_领取锦囊.enabled"
                v-model="taskConfig.起号_领取锦囊.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_领取锦囊.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="式神养成">
              <el-switch
                v-model="taskConfig.起号_式神养成.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.起号_式神养成.enabled"
                v-model="taskConfig.起号_式神养成.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_式神养成.enabled"
                v-model="taskConfig.起号_式神养成.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_式神养成.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="升级饭盒">
              <el-switch
                v-model="taskConfig.起号_升级饭盒.enabled"
                @change="updateTaskConfigData"
              />
              <span style="margin-left: 10px; font-size: 13px;">
                <span :style="{ color: (selectedAccount?.fanhe_level ?? 0) >= 10 ? '#67C23A' : '#606266' }">
                  饭盒 Lv.{{ selectedAccount?.fanhe_level ?? 0 }}
                </span>
                /
                <span :style="{ color: (selectedAccount?.jiuhu_level ?? 0) >= 10 ? '#67C23A' : '#606266' }">
                  酒壶 Lv.{{ selectedAccount?.jiuhu_level ?? 0 }}
                </span>
              </span>
              <el-date-picker
                v-if="taskConfig.起号_升级饭盒.enabled"
                v-model="taskConfig.起号_升级饭盒.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.起号_升级饭盒.enabled"
                v-model="taskConfig.起号_升级饭盒.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.起号_升级饭盒.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'init'" label="领取成就奖励">
              <el-switch
                v-model="taskConfig.领取成就奖励.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取成就奖励.enabled"
                v-model="taskConfig.领取成就奖励.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.领取成就奖励.enabled"
                v-model="taskConfig.领取成就奖励.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.领取成就奖励.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <!-- === 正常专属任务（仅 ok 状态显示）=== -->
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="寄养">
              <el-switch
                v-model="taskConfig.寄养.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.寄养.enabled"
                v-model="taskConfig.寄养.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.寄养.enabled"
                v-model="taskConfig.寄养.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.寄养.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="悬赏">
              <el-switch
                v-model="taskConfig.悬赏.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.悬赏.enabled"
                v-model="taskConfig.悬赏.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.悬赏.enabled"
                v-model="taskConfig.悬赏.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.悬赏.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="弥助">
              <el-switch
                v-model="taskConfig.弥助.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.弥助.enabled"
                v-model="taskConfig.弥助.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.弥助.enabled"
                v-model="taskConfig.弥助.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.弥助.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="勾协">
              <el-switch
                v-model="taskConfig.勾协.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.勾协.enabled"
                v-model="taskConfig.勾协.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.勾协.enabled"
                v-model="taskConfig.勾协.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.勾协.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="探索突破">
              <el-switch
                v-model="taskConfig.探索突破.enabled"
                @change="updateTaskConfigData"
              />
              <template v-if="taskConfig.探索突破.enabled">
                <el-checkbox
                  v-model="taskConfig.探索突破.sub_explore"
                  style="margin-left: 15px"
                  @change="onExploreSubOptionChange"
                >探索</el-checkbox>
                <el-checkbox
                  v-model="taskConfig.探索突破.sub_tupo"
                  @change="onExploreSubOptionChange"
                >突破</el-checkbox>
              </template>
              <el-date-picker
                v-if="taskConfig.探索突破.enabled"
                v-model="taskConfig.探索突破.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.探索突破.enabled"
                v-model="taskConfig.探索突破.stamina_threshold"
                :min="0"
                :max="99999"
                placeholder="保留体力"
                style="margin-left: 10px; width: 150px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.探索突破.enabled" class="config-item">保留体力</span>
              <el-input-number
                v-if="taskConfig.探索突破.enabled"
                v-model="taskConfig.探索突破.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.探索突破.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="结界卡合成">
              <el-switch
                v-model="taskConfig.结界卡合成.enabled"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.结界卡合成.enabled" style="margin-left: 10px">
                已探索：
                <el-input-number
                  v-model="taskConfig.结界卡合成.explore_count"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 80px; margin: 0 5px"
                  @change="updateTaskConfigData"
                />
                /40 次
              </span>
            </el-form-item>
            <el-form-item label="加好友">
              <el-switch
                v-model="taskConfig.加好友.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.加好友.enabled"
                v-model="taskConfig.加好友.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.加好友.enabled"
                v-model="taskConfig.加好友.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.加好友.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="领取登录礼包">
              <el-switch
                v-model="taskConfig.领取登录礼包.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取登录礼包.enabled"
                v-model="taskConfig.领取登录礼包.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.领取登录礼包.enabled"
                v-model="taskConfig.领取登录礼包.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.领取登录礼包.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="领取饭盒酒壶">
              <el-switch
                v-model="taskConfig.领取饭盒酒壶.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取饭盒酒壶.enabled"
                v-model="taskConfig.领取饭盒酒壶.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.领取饭盒酒壶.enabled"
                v-model="taskConfig.领取饭盒酒壶.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.领取饭盒酒壶.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="领取邮件">
              <el-switch
                v-model="taskConfig.领取邮件.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取邮件.enabled"
                v-model="taskConfig.领取邮件.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.领取邮件.enabled"
                v-model="taskConfig.领取邮件.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.领取邮件.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="爬塔">
              <el-switch
                v-model="taskConfig.爬塔.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.爬塔.enabled"
                v-model="taskConfig.爬塔.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.爬塔.enabled"
                v-model="taskConfig.爬塔.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.爬塔.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="逢魔">
              <el-switch
                v-model="taskConfig.逢魔.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.逢魔.enabled"
                v-model="taskConfig.逢魔.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.逢魔.enabled"
                v-model="taskConfig.逢魔.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.逢魔.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="地鬼">
              <el-switch
                v-model="taskConfig.地鬼.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.地鬼.enabled"
                v-model="taskConfig.地鬼.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.地鬼.enabled"
                v-model="taskConfig.地鬼.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.地鬼.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="道馆">
              <el-switch
                v-model="taskConfig.道馆.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.道馆.enabled"
                v-model="taskConfig.道馆.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.道馆.enabled"
                v-model="taskConfig.道馆.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.道馆.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="寮商店">
              <el-switch
                v-model="taskConfig.寮商店.enabled"
                @change="updateTaskConfigData"
              />
              <span style="margin-left: 10px; font-size: 13px;">
                <span :style="{ color: (selectedAccount?.liao_level ?? 0) >= 5 ? '#67C23A' : '#E6A23C' }">
                  寮 Lv.{{ selectedAccount?.liao_level ?? 0 }}
                </span>
              </span>
              <el-date-picker
                v-if="taskConfig.寮商店.enabled"
                v-model="taskConfig.寮商店.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <template v-if="taskConfig.寮商店.enabled">
                <el-checkbox
                  v-model="taskConfig.寮商店.buy_heisui"
                  style="margin-left: 10px"
                  @change="onLiaoShopOptionChange"
                >黑碎(200功勋)</el-checkbox>
                <el-checkbox
                  v-model="taskConfig.寮商店.buy_lanpiao"
                  @change="onLiaoShopOptionChange"
                >蓝票(120功勋×2)</el-checkbox>
                <el-input-number
                  v-model="taskConfig.寮商店.fail_delay"
                  :min="1"
                  :max="1440"
                  style="margin-left: 10px; width: 130px"
                  @change="updateTaskConfigData"
                />
                <span class="config-item">分钟延迟</span>
              </template>
            </el-form-item>
            <el-form-item label="领取寮金币">
              <el-switch
                v-model="taskConfig.领取寮金币.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取寮金币.enabled"
                v-model="taskConfig.领取寮金币.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.领取寮金币.enabled"
                v-model="taskConfig.领取寮金币.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.领取寮金币.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="每日一抽">
              <el-switch
                v-model="taskConfig.每日一抽.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.每日一抽.enabled"
                v-model="taskConfig.每日一抽.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.每日一抽.enabled"
                v-model="taskConfig.每日一抽.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.每日一抽.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="每周商店">
              <el-switch
                v-model="taskConfig.每周商店.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.每周商店.enabled"
                v-model="taskConfig.每周商店.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <template v-if="taskConfig.每周商店.enabled">
                <el-checkbox
                  v-model="taskConfig.每周商店.buy_lanpiao"
                  style="margin-left: 10px"
                  @change="updateTaskConfigData"
                >蓝票(180勋章)</el-checkbox>
                <el-checkbox
                  v-model="taskConfig.每周商店.buy_heidan"
                  @change="updateTaskConfigData"
                >黑蛋(480勋章)</el-checkbox>
                <el-checkbox
                  v-model="taskConfig.每周商店.buy_tili"
                  @change="updateTaskConfigData"
                >体力(120勋章)</el-checkbox>
                <el-input-number
                  v-model="taskConfig.每周商店.fail_delay"
                  :min="1"
                  :max="1440"
                  style="margin-left: 10px; width: 130px"
                  @change="updateTaskConfigData"
                />
                <span class="config-item">分钟延迟</span>
              </template>
            </el-form-item>
            <el-form-item v-if="selectedAccount?.progress === 'ok'" label="秘闻">
              <el-switch
                v-model="taskConfig.秘闻.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.秘闻.enabled"
                v-model="taskConfig.秘闻.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.秘闻.enabled"
                v-model="taskConfig.秘闻.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.秘闻.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="每周分享">
              <el-switch
                v-model="taskConfig.每周分享.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.每周分享.enabled"
                v-model="taskConfig.每周分享.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.每周分享.enabled"
                v-model="taskConfig.每周分享.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.每周分享.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="召唤礼包">
              <el-switch
                v-model="taskConfig.召唤礼包.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.召唤礼包.enabled"
                v-model="taskConfig.召唤礼包.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.召唤礼包.enabled"
                v-model="taskConfig.召唤礼包.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.召唤礼包.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="签到">
              <el-switch
                v-model="taskConfig.签到.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.签到.enabled"
                v-model="taskConfig.签到.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.签到.enabled"
                v-model="taskConfig.签到.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.签到.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
            <el-form-item label="御魂">
              <el-switch
                v-model="taskConfig.御魂.enabled"
                @change="updateTaskConfigData"
              />
              <template v-if="taskConfig.御魂.enabled">
                <span style="margin-left: 10px">次数:</span>
                <el-input-number
                  v-model="taskConfig.御魂.run_count"
                  :min="0"
                  :max="200"
                  size="small"
                  style="margin-left: 5px; width: 100px"
                  @change="onYuhunRunCountChange"
                />
                <span style="margin-left: 10px">目标层:</span>
                <el-select
                  v-model="taskConfig.御魂.target_level"
                  size="small"
                  style="margin-left: 5px; width: 80px"
                  @change="updateTaskConfigData"
                >
                  <el-option
                    v-for="n in 10"
                    :key="n"
                    :label="n + '层'"
                    :value="n"
                  />
                </el-select>
                <span style="margin-left: 10px; color: #909399">
                  剩余: {{ taskConfig.御魂.remaining_count }}
                </span>
                <span style="margin-left: 10px;" :style="{
                  color: taskConfig.御魂.unlocked_count >= taskConfig.御魂.target_level ? '#67C23A' : '#E6A23C'
                }">
                  解锁: {{ taskConfig.御魂.unlocked_count || 0 }}/{{ taskConfig.御魂.target_level || 10 }}
                  <template v-if="taskConfig.御魂.unlocked_count >= taskConfig.御魂.target_level">(已完成)</template>
                </span>
                <span style="margin-left: 10px">失败延迟:</span>
                <el-input-number
                  v-model="taskConfig.御魂.fail_delay"
                  :min="1"
                  :max="5760"
                  style="margin-left: 5px; width: 130px"
                  @change="updateTaskConfigData"
                />
                <span class="config-item">分钟</span>
              </template>
            </el-form-item>
            <el-form-item label="斗技">
              <el-switch
                v-model="taskConfig.斗技.enabled"
                @change="updateTaskConfigData"
              />
              <template v-if="taskConfig.斗技.enabled">
                <span style="margin-left: 10px">时间:</span>
                <el-select
                  v-model="taskConfig.斗技.start_hour"
                  size="small"
                  style="margin-left: 5px; width: 90px"
                  @change="onDoujiStartHourChange"
                >
                  <el-option
                    v-for="h in 11"
                    :key="h + 11"
                    :label="(h + 11) + ':00'"
                    :value="h + 11"
                  />
                </el-select>
                <span style="margin: 0 5px">至</span>
                <el-select
                  v-model="taskConfig.斗技.end_hour"
                  size="small"
                  style="width: 90px"
                  @change="updateTaskConfigData"
                >
                  <el-option
                    v-for="h in (23 - taskConfig.斗技.start_hour)"
                    :key="taskConfig.斗技.start_hour + h"
                    :label="(taskConfig.斗技.start_hour + h) + ':00'"
                    :value="taskConfig.斗技.start_hour + h"
                  />
                </el-select>
                <span style="margin-left: 10px">模式:</span>
                <el-radio-group
                  v-model="taskConfig.斗技.mode"
                  size="small"
                  style="margin-left: 5px"
                  @change="updateTaskConfigData"
                >
                  <el-radio label="honor">刷满荣誉</el-radio>
                  <el-radio label="score">刷到分数</el-radio>
                </el-radio-group>
                <el-input-number
                  v-if="taskConfig.斗技.mode === 'score'"
                  v-model="taskConfig.斗技.target_score"
                  :min="1000"
                  :max="3000"
                  :step="100"
                  size="small"
                  style="margin-left: 5px; width: 120px"
                  @change="updateTaskConfigData"
                />
                <el-date-picker
                  v-model="taskConfig.斗技.next_time"
                  type="datetime"
                  placeholder="下次执行时间"
                  format="YYYY-MM-DD HH:mm"
                  value-format="YYYY-MM-DD HH:mm"
                  style="margin-left: 10px; width: 200px"
                  @change="updateTaskConfigData"
                />
                <el-input-number
                  v-model="taskConfig.斗技.fail_delay"
                  :min="1"
                  :max="1440"
                  style="margin-left: 10px; width: 130px"
                  @change="updateTaskConfigData"
                />
                <span class="config-item">分钟延迟</span>
              </template>
            </el-form-item>
            <el-form-item label="对弈竞猜">
              <el-switch
                v-model="taskConfig.对弈竞猜.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.对弈竞猜.enabled"
                v-model="taskConfig.对弈竞猜.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.对弈竞猜.enabled"
                v-model="taskConfig.对弈竞猜.fail_delay"
                :min="1"
                :max="1440"
                style="margin-left: 10px; width: 130px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.对弈竞猜.enabled" class="config-item">分钟延迟</span>
            </el-form-item>
          </el-form>

          <!-- 休息配置 -->
          <el-divider>休息配置</el-divider>
          <el-alert
            v-if="!globalRestEnabled"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
          >
            <template #title>
              全局休息开关已关闭，所有账号的休息设置不会生效。如需启用请前往系统配置页修改。
            </template>
          </el-alert>
          <el-form label-width="100px">
            <el-form-item label="启用休息">
              <el-switch v-model="restConfig.enabled" @change="updateRestConfigData" />
            </el-form-item>
            <template v-if="restConfig.enabled">
              <el-form-item label="休息模式">
                <el-radio-group
                  v-model="restConfig.mode"
                  @change="updateRestConfigData"
                >
                  <el-radio label="random">随机（2-3小时）</el-radio>
                  <el-radio label="custom">自定义</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="restConfig.mode === 'custom'" label="开始时间">
                <el-time-picker
                  v-model="restConfig.start_time"
                  format="HH:mm"
                  value-format="HH:mm"
                  placeholder="选择时间"
                  @change="updateRestConfigData"
                />
              </el-form-item>
              <el-form-item v-if="restConfig.mode === 'custom'" label="持续时长">
                <el-input-number
                  v-model="restConfig.duration"
                  :min="1"
                  :max="5"
                  @change="updateRestConfigData"
                />
                小时
              </el-form-item>
            </template>
          </el-form>

          <!-- 今日休息时段 -->
          <el-divider>今日休息时段</el-divider>
          <div class="rest-plan">
            <template v-if="!restConfig.enabled">
              <el-tag type="info">休息功能已关闭</el-tag>
            </template>
            <template v-else>
              <el-tag v-if="restPlan.start_time">
                {{ restPlan.start_time }} - {{ restPlan.end_time }}
              </el-tag>
              <span v-else>暂无休息计划</span>
            </template>
          </div>
        </el-card>

        <el-empty v-else description="请选择一个账号查看详情" />
      </el-col>
    </el-row>

    <!-- 添加游戏账号对话框 -->
    <el-dialog
      v-model="gameDialogVisible"
      title="添加ID账号"
      width="400px"
    >
      <el-form :model="gameForm" label-width="80px">
        <el-form-item label="账号ID" required>
          <el-input v-model="gameForm.login_id" placeholder="请输入账号ID" />
        </el-form-item>
        <el-form-item label="等级">
          <el-input-number v-model="gameForm.level" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="体力">
          <el-input-number v-model="gameForm.stamina" :min="0" :max="99999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="gameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddGame">确定</el-button>
      </template>
    </el-dialog>

    <!-- 配置阵容对话框 -->
    <el-dialog
      v-model="lineupDialogVisible"
      :title="`配置阵容 - ${selectedAccount?.login_id || ''}`"
      width="500px"
    >
      <el-table :data="lineupTableData" border style="width: 100%">
        <el-table-column prop="task" label="任务" width="100" />
        <el-table-column label="分组" width="180">
          <template #default="{ row }">
            <el-select v-model="row.group" size="small" style="width: 100%">
              <el-option v-for="n in 7" :key="n" :label="`分组${n}`" :value="n" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="阵容" width="180">
          <template #default="{ row }">
            <el-select v-model="row.position" size="small" style="width: 100%">
              <el-option v-for="n in 7" :key="n" :label="`阵容${n}`" :value="n" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="lineupDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveLineupConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  getAccounts,
  createGameAccount,
  updateAccount,
  updateTaskConfig,
  updateRestConfig,
  getRestConfig,
  getRestPlan,
  deleteGameAccount,
  deleteGameAccounts,
  getLineupConfig,
  updateLineupConfig,
  updateShikigamiConfig
} from '@/api/accounts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { API_ENDPOINTS, apiRequest } from '@/config'

// 全局休息开关状态
const globalRestEnabled = ref(true)

// 数据
const accountTree = ref([])
const searchText = ref('')
const statusFilter = ref('')
const selectedAccount = ref(null)
const accountTreeRef = ref(null)
const selectedGameIds = ref([])
const taskConfig = reactive({
  寄养: { enabled: true, next_time: "2020-01-01 00:00" },
  悬赏: { enabled: true, next_time: "2020-01-01 00:00" },
  弥助: { enabled: true, next_time: "2020-01-01 00:00" },
  勾协: { enabled: true, next_time: "2020-01-01 00:00" },
  探索突破: { enabled: true, sub_explore: true, sub_tupo: true, stamina_threshold: 1000, next_time: "2020-01-01 00:00", fail_delay: 30 },
  结界卡合成: { enabled: true, explore_count: 0 },
  加好友: { enabled: true, next_time: "2020-01-01 00:00" },
  领取登录礼包: { enabled: true, next_time: "2020-01-01 00:00" },
  领取饭盒酒壶: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  领取邮件: { enabled: true, next_time: "2020-01-01 00:00" },
  爬塔: { enabled: true, next_time: "2020-01-01 00:00" },
  逢魔: { enabled: true, next_time: "2020-01-01 00:00" },
  地鬼: { enabled: true, next_time: "2020-01-01 00:00" },
  道馆: { enabled: true, next_time: "2020-01-01 00:00" },
  寮商店: { enabled: true, next_time: "2020-01-01 00:00", buy_heisui: true, buy_lanpiao: true },
  领取寮金币: { enabled: true, next_time: "2020-01-01 00:00" },
  每日一抽: { enabled: true, next_time: "2020-01-01 00:00" },
  每周商店: { enabled: true, next_time: "2020-01-01 00:00", buy_lanpiao: true, buy_heidan: true, buy_tili: true },
  秘闻: { enabled: true, next_time: "2020-01-01 00:00" },
  签到: { enabled: false, next_time: "2020-01-01 00:00", fail_delay: 30 },
  御魂: { enabled: false, run_count: 0, remaining_count: 0, unlocked_count: 0, target_level: 10, fail_delay: 2880 },
  斗技: { enabled: false, start_hour: 12, end_hour: 23, mode: 'honor', target_score: 2000, next_time: "2020-01-01 00:00", fail_delay: 30 },
  对弈竞猜: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  每周分享: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  召唤礼包: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_领取奖励: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_租借式神: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_新手任务: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_经验副本: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_领取锦囊: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_式神养成: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  起号_升级饭盒: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
  领取成就奖励: { enabled: true, next_time: "2020-01-01 00:00", fail_delay: 30 },
})
const restConfig = reactive({
  enabled: true,
  mode: 'random',
  start_time: '',
  duration: 2
})
const restPlan = ref({})

// 对话框
const gameDialogVisible = ref(false)
const gameForm = reactive({
  login_id: '',
  level: 1,
  stamina: 0
})

// 阵容配置
const lineupDialogVisible = ref(false)
const LINEUP_TASKS = ['逢魔', '地鬼', '探索', '结界突破', '道馆', '秘闻', '御魂']

// 式神状态配置
const shikigamiConfig = reactive({
  座敷童子: {
    yuhun: '',
    awakened: false,
    star: 1,
    skill_level: 1
  },
  租借式神: []
})

// 御魂套装选项列表
const yuhunOptions = [
  '招财猫', '火灵', '地藏像', '镜姬', '涅槃之火', '被服',
  '日女巳时', '狂骨', '轮入道', '网切', '心眼', '针女',
  '破势', '魅妖', '珍珠', '树妖', '薙魂', '魍魉之匣'
]
const lineupConfig = reactive({})
const lineupTableData = ref(LINEUP_TASKS.map(task => ({
  task,
  group: 1,
  position: 1
})))

// 树形控件配置
const treeProps = {
  children: 'children',
  label: 'label'
}

// 过滤后的树数据（按 login_id 模糊匹配 + 状态筛选）
const filteredAccountTree = computed(() => {
  const q = (searchText.value || '').trim().toLowerCase()
  const sf = statusFilter.value

  const matchNode = (node) => {
    if (sf && node.status !== sf) return false
    if (q) {
      const loginMatch = String(node.login_id ?? '').toLowerCase().includes(q)
      const remarkMatch = String(node.remark ?? '').toLowerCase().includes(q)
      if (!loginMatch && !remarkMatch) return false
    }
    return true
  }

  if (!q && !sf) return accountTree.value
  return accountTree.value.filter(node => matchNode(node))
})

// 获取账号列表
const fetchAccounts = async () => {
  try {
    const data = await getAccounts()
    accountTree.value = formatAccountTree(data)
  } catch (error) {
    ElMessage.error('获取账号列表失败')
  }
}

// 格式化账号树
const formatAccountTree = (data) => {
  return data.map(item => ({
    ...item,
    label: item.login_id
  }))
}

// 勾选变化，收集被选中的游戏账号ID
const handleTreeCheck = () => {
  const keys = accountTreeRef.value?.getCheckedKeys(false) || []
  const ids = keys
    .map(k => (typeof k === 'string' && /^\d+$/.test(k)) ? Number(k) : k)
    .filter(k => typeof k === 'number')
  selectedGameIds.value = ids
}

// 是否已全选（基于筛选后的列表）
const isAllSelected = computed(() => {
  const total = filteredAccountTree.value.length
  return total > 0 && selectedGameIds.value.length === total
})

// 全选/取消全选
const handleSelectAll = () => {
  if (isAllSelected.value) {
    accountTreeRef.value.setCheckedKeys([])
  } else {
    const allIds = filteredAccountTree.value.map(item => item.id)
    accountTreeRef.value.setCheckedKeys(allIds)
  }
  handleTreeCheck()
}

// 批量删除
const handleBatchDelete = async () => {
  if (!selectedGameIds.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedGameIds.value.length} 个账号？此操作不可恢复`, '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await deleteGameAccounts(selectedGameIds.value)
    ElMessage.success('批量删除成功')
    if (accountTreeRef.value) accountTreeRef.value.setCheckedKeys([])
    selectedGameIds.value = []
    selectedAccount.value = null
    restPlan.value = {}
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('批量删除失败')
  }
}

// 处理节点点击
const handleNodeClick = async (data) => {
  if (data.type === 'game') {
    selectedAccount.value = data
    // 加载任务配置，支持新的配置结构
    const savedConfig = data.task_config || {}

    // 寄养：支持next_time，默认2020年
    taskConfig.寄养 = {
      enabled: savedConfig.寄养?.enabled === true,
      next_time: savedConfig.寄养?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.寄养?.fail_delay ?? 30,
    }

    // 悬赏：支持next_time，默认2020年
    taskConfig.悬赏 = {
      enabled: savedConfig.悬赏?.enabled === true,
      next_time: savedConfig.悬赏?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.悬赏?.fail_delay ?? 30,
    }

    // 弥助：支持next_time，默认2020年
    taskConfig.弥助 = {
      enabled: savedConfig.弥助?.enabled === true,
      next_time: savedConfig.弥助?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.弥助?.fail_delay ?? 30,
    }

    // 勾协：支持next_time，默认2020年
    taskConfig.勾协 = {
      enabled: savedConfig.勾协?.enabled === true,
      next_time: savedConfig.勾协?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.勾协?.fail_delay ?? 30,
    }

    // 探索突破：支持stamina_threshold + next_time + sub_explore/sub_tupo
    if (savedConfig.探索突破) {
      taskConfig.探索突破 = {
        enabled: savedConfig.探索突破.enabled === true,
        sub_explore: savedConfig.探索突破.sub_explore !== false,
        sub_tupo: savedConfig.探索突破.sub_tupo !== false,
        stamina_threshold: savedConfig.探索突破.stamina_threshold ?? 1000,
        next_time: savedConfig.探索突破.next_time ?? "2020-01-01 00:00",
        fail_delay: savedConfig.探索突破.fail_delay ?? 30,
      }
    } else {
      // 兼容旧数据
      const exploreEnabled = savedConfig.探索?.enabled === true
      const breakthroughEnabled = savedConfig.突破?.enabled === true
      taskConfig.探索突破 = {
        enabled: exploreEnabled || breakthroughEnabled,
        sub_explore: true,
        sub_tupo: true,
        stamina_threshold: 1000,
        next_time: "2020-01-01 00:00",
        fail_delay: 30,
      }
    }

    // 结界卡合成：支持explore_count
    taskConfig.结界卡合成 = {
      enabled: savedConfig.结界卡合成?.enabled === true,
      explore_count: savedConfig.结界卡合成?.explore_count ?? 0
    }

    // 加好友：支持next_time，默认2020年
    taskConfig.加好友 = {
      enabled: savedConfig.加好友?.enabled === true,
      next_time: savedConfig.加好友?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.加好友?.fail_delay ?? 30,
    }

    // 领取登录礼包：支持next_time，默认2020年
    taskConfig.领取登录礼包 = {
      enabled: savedConfig.领取登录礼包?.enabled === true,
      next_time: savedConfig.领取登录礼包?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.领取登录礼包?.fail_delay ?? 30,
    }

    // 领取饭盒酒壶：支持next_time，默认2020年
    taskConfig.领取饭盒酒壶 = {
      enabled: savedConfig.领取饭盒酒壶?.enabled === true,
      next_time: savedConfig.领取饭盒酒壶?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.领取饭盒酒壶?.fail_delay ?? 30,
    }

    // 领取邮件：支持next_time，默认2020年
    taskConfig.领取邮件 = {
      enabled: savedConfig.领取邮件?.enabled === true,
      next_time: savedConfig.领取邮件?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.领取邮件?.fail_delay ?? 30,
    }

    // 爬塔：支持next_time，默认2020年
    taskConfig.爬塔 = {
      enabled: savedConfig.爬塔?.enabled === true,
      next_time: savedConfig.爬塔?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.爬塔?.fail_delay ?? 30,
    }

    // 逢魔：支持next_time，默认2020年
    taskConfig.逢魔 = {
      enabled: savedConfig.逢魔?.enabled === true,
      next_time: savedConfig.逢魔?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.逢魔?.fail_delay ?? 30,
    }

    // 地鬼：支持next_time，默认2020年
    taskConfig.地鬼 = {
      enabled: savedConfig.地鬼?.enabled === true,
      next_time: savedConfig.地鬼?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.地鬼?.fail_delay ?? 30,
    }

    // 道馆：支持next_time，默认2020年
    taskConfig.道馆 = {
      enabled: savedConfig.道馆?.enabled === true,
      next_time: savedConfig.道馆?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.道馆?.fail_delay ?? 30,
    }

    // 寮商店：支持next_time + buy_heisui/buy_lanpiao
    taskConfig.寮商店 = {
      enabled: savedConfig.寮商店?.enabled === true,
      next_time: savedConfig.寮商店?.next_time ?? "2020-01-01 00:00",
      buy_heisui: savedConfig.寮商店?.buy_heisui !== false,
      buy_lanpiao: savedConfig.寮商店?.buy_lanpiao !== false,
      fail_delay: savedConfig.寮商店?.fail_delay ?? 30,
    }

    // 领取寮金币：支持next_time，默认2020年
    taskConfig.领取寮金币 = {
      enabled: savedConfig.领取寮金币?.enabled === true,
      next_time: savedConfig.领取寮金币?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.领取寮金币?.fail_delay ?? 30,
    }

    // 每日一抽：支持next_time，默认2020年
    taskConfig.每日一抽 = {
      enabled: savedConfig.每日一抽?.enabled === true,
      next_time: savedConfig.每日一抽?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.每日一抽?.fail_delay ?? 30,
    }

    // 每周商店：支持next_time + buy_lanpiao/buy_heidan/buy_tili
    taskConfig.每周商店 = {
      enabled: savedConfig.每周商店?.enabled === true,
      next_time: savedConfig.每周商店?.next_time ?? "2020-01-01 00:00",
      buy_lanpiao: savedConfig.每周商店?.buy_lanpiao !== false,
      buy_heidan: savedConfig.每周商店?.buy_heidan !== false,
      buy_tili: savedConfig.每周商店?.buy_tili !== false,
      fail_delay: savedConfig.每周商店?.fail_delay ?? 30,
    }

    // 秘闻：支持next_time，默认2020年
    taskConfig.秘闻 = {
      enabled: savedConfig.秘闻?.enabled === true,
      next_time: savedConfig.秘闻?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.秘闻?.fail_delay ?? 30,
    }

    // 签到：独立任务，按 next_time 调度
    taskConfig.签到 = {
      enabled: savedConfig.签到?.enabled === true,
      next_time: savedConfig.签到?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.签到?.fail_delay ?? 30,
    }

    // 御魂：次数驱动型任务
    taskConfig.御魂 = {
      enabled: savedConfig.御魂?.enabled === true,
      run_count: savedConfig.御魂?.run_count ?? 0,
      remaining_count: savedConfig.御魂?.remaining_count ?? 0,
      unlocked_count: savedConfig.御魂?.unlocked_count ?? 0,
      target_level: savedConfig.御魂?.target_level ?? 10,
      fail_delay: savedConfig.御魂?.fail_delay ?? 2880,
    }

    // 斗技：时间窗口 + 模式选择
    taskConfig.斗技 = {
      enabled: savedConfig.斗技?.enabled === true,
      start_hour: savedConfig.斗技?.start_hour ?? 12,
      end_hour: savedConfig.斗技?.end_hour ?? 23,
      mode: savedConfig.斗技?.mode ?? 'honor',
      target_score: savedConfig.斗技?.target_score ?? 2000,
      next_time: savedConfig.斗技?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.斗技?.fail_delay ?? 30,
    }

    // 对弈竞猜
    taskConfig.对弈竞猜 = {
      enabled: savedConfig.对弈竞猜?.enabled === true,
      next_time: savedConfig.对弈竞猜?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.对弈竞猜?.fail_delay ?? 30,
    }

    // 每周分享：支持next_time
    taskConfig.每周分享 = {
      enabled: savedConfig.每周分享?.enabled === true,
      next_time: savedConfig.每周分享?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.每周分享?.fail_delay ?? 30,
    }

    // 召唤礼包：支持next_time
    taskConfig.召唤礼包 = {
      enabled: savedConfig.召唤礼包?.enabled === true,
      next_time: savedConfig.召唤礼包?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.召唤礼包?.fail_delay ?? 30,
    }

    // 起号任务解析
    taskConfig.起号_领取奖励 = {
      enabled: savedConfig.起号_领取奖励?.enabled === true,
      next_time: savedConfig.起号_领取奖励?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_领取奖励?.fail_delay ?? 30,
    }
    taskConfig.起号_租借式神 = {
      enabled: savedConfig.起号_租借式神?.enabled === true,
      next_time: savedConfig.起号_租借式神?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_租借式神?.fail_delay ?? 30,
    }
    taskConfig.起号_新手任务 = {
      enabled: savedConfig.起号_新手任务?.enabled === true,
      next_time: savedConfig.起号_新手任务?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_新手任务?.fail_delay ?? 30,
    }
    taskConfig.起号_经验副本 = {
      enabled: savedConfig.起号_经验副本?.enabled === true,
      next_time: savedConfig.起号_经验副本?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_经验副本?.fail_delay ?? 30,
    }
    taskConfig.起号_领取锦囊 = {
      enabled: savedConfig.起号_领取锦囊?.enabled === true,
      next_time: savedConfig.起号_领取锦囊?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_领取锦囊?.fail_delay ?? 30,
    }
    taskConfig.起号_式神养成 = {
      enabled: savedConfig.起号_式神养成?.enabled === true,
      next_time: savedConfig.起号_式神养成?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_式神养成?.fail_delay ?? 30,
    }
    taskConfig.起号_升级饭盒 = {
      enabled: savedConfig.起号_升级饭盒?.enabled === true,
      next_time: savedConfig.起号_升级饭盒?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.起号_升级饭盒?.fail_delay ?? 30,
    }

    taskConfig.领取成就奖励 = {
      enabled: savedConfig.领取成就奖励?.enabled === true,
      next_time: savedConfig.领取成就奖励?.next_time ?? "2020-01-01 00:00",
      fail_delay: savedConfig.领取成就奖励?.fail_delay ?? 30,
    }

    // 加载休息配置
    const rc = data.rest_config || {}
    restConfig.enabled = rc.enabled !== false
    restConfig.mode = rc.mode || 'random'
    restConfig.start_time = rc.start_time || ''
    restConfig.duration = rc.duration || 2

    // 获取休息计划
    try {
      const plan = await getRestPlan(data.id)
      restPlan.value = plan
    } catch (error) {
      restPlan.value = {}
    }

    // 加载式神状态配置（仅 init 阶段）
    if (data.progress === 'init') {
      const sConfig = data.shikigami_config || {}
      shikigamiConfig.座敷童子 = {
        yuhun: sConfig.座敷童子?.yuhun ?? '',
        awakened: sConfig.座敷童子?.awakened ?? false,
        star: sConfig.座敷童子?.star ?? 1,
        skill_level: sConfig.座敷童子?.skill_level ?? 1
      }
      shikigamiConfig.租借式神 = sConfig.租借式神 || []
    }
  }
}

// 更新账号信息
const updateAccountInfo = async () => {
  if (!selectedAccount.value) return

  try {
    const response = await updateAccount(selectedAccount.value.id, {
      status: selectedAccount.value.status,
      progress: selectedAccount.value.progress,
      level: selectedAccount.value.level,
      stamina: selectedAccount.value.stamina,
      remark: selectedAccount.value.remark
    })

    // 如果后端返回了新的 task_config（progress 切换时），更新本地数据
    if (response?.task_config) {
      selectedAccount.value.task_config = response.task_config
      // 重新解析任务配置以刷新表单
      handleNodeClick(selectedAccount.value)
    }

    // 更新账号树中的数据
    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.status = selectedAccount.value.status
          node.progress = selectedAccount.value.progress
          node.level = selectedAccount.value.level
          node.stamina = selectedAccount.value.stamina
          node.remark = selectedAccount.value.remark
          if (response?.task_config) {
            node.task_config = response.task_config
          }
          break
        }
      }
    }
    updateAccountInTree(accountTree.value)

    ElMessage.success('账号信息已更新')
  } catch (error) {
    ElMessage.error('更新失败')
  }
}

// 寮商店子选项变更：至少勾选一个
const onLiaoShopOptionChange = () => {
  if (!taskConfig.寮商店.buy_heisui && !taskConfig.寮商店.buy_lanpiao) {
    ElMessage.warning('寮商店至少需要勾选一个购买选项')
    // 恢复刚取消的选项
    taskConfig.寮商店.buy_heisui = true
    return
  }
  updateTaskConfigData()
}

// 御魂次数变更：同步 remaining_count
const onYuhunRunCountChange = () => {
  taskConfig.御魂.remaining_count = taskConfig.御魂.run_count
  updateTaskConfigData()
}

const onDoujiStartHourChange = () => {
  if (taskConfig.斗技.end_hour <= taskConfig.斗技.start_hour) {
    taskConfig.斗技.end_hour = taskConfig.斗技.start_hour + 1
  }
  updateTaskConfigData()
}

// 探索子选项变更：至少勾选一个
const onExploreSubOptionChange = () => {
  if (!taskConfig.探索突破.sub_explore && !taskConfig.探索突破.sub_tupo) {
    ElMessage.warning('探索和突破至少需要勾选一个')
    taskConfig.探索突破.sub_explore = true
    return
  }
  updateTaskConfigData()
}

// 更新任务配置
// Update task config
const updateTaskConfigData = async () => {
  if (!selectedAccount.value) return

  try {
    const isInit = selectedAccount.value?.progress === 'init'

    // 共享任务（始终包含）
    const configToSend = {
      "探索突破": {
        enabled: taskConfig["探索突破"].enabled,
        sub_explore: taskConfig["探索突破"].sub_explore,
        sub_tupo: taskConfig["探索突破"].sub_tupo,
        stamina_threshold: taskConfig["探索突破"].stamina_threshold,
        next_time: taskConfig["探索突破"].next_time,
        fail_delay: taskConfig["探索突破"].fail_delay,
      },
      "地鬼": {
        enabled: taskConfig["地鬼"].enabled,
        next_time: taskConfig["地鬼"].next_time,
        fail_delay: taskConfig["地鬼"].fail_delay,
      },
      "寮商店": {
        enabled: taskConfig["寮商店"].enabled,
        next_time: taskConfig["寮商店"].next_time,
        buy_heisui: taskConfig["寮商店"].buy_heisui,
        buy_lanpiao: taskConfig["寮商店"].buy_lanpiao,
        fail_delay: taskConfig["寮商店"].fail_delay,
      },
      "领取寮金币": {
        enabled: taskConfig["领取寮金币"].enabled,
        next_time: taskConfig["领取寮金币"].next_time,
        fail_delay: taskConfig["领取寮金币"].fail_delay,
      },
      "每周商店": {
        enabled: taskConfig["每周商店"].enabled,
        next_time: taskConfig["每周商店"].next_time,
        buy_lanpiao: taskConfig["每周商店"].buy_lanpiao,
        buy_heidan: taskConfig["每周商店"].buy_heidan,
        buy_tili: taskConfig["每周商店"].buy_tili,
        fail_delay: taskConfig["每周商店"].fail_delay,
      },
      "领取邮件": {
        enabled: taskConfig["领取邮件"].enabled,
        next_time: taskConfig["领取邮件"].next_time,
        fail_delay: taskConfig["领取邮件"].fail_delay,
      },
      "签到": {
        enabled: taskConfig["签到"].enabled,
        next_time: taskConfig["签到"].next_time,
        fail_delay: taskConfig["签到"].fail_delay
      },
      "领取登录礼包": {
        enabled: taskConfig["领取登录礼包"].enabled,
        next_time: taskConfig["领取登录礼包"].next_time,
        fail_delay: taskConfig["领取登录礼包"].fail_delay,
      },
      "领取饭盒酒壶": {
        enabled: taskConfig["领取饭盒酒壶"].enabled,
        next_time: taskConfig["领取饭盒酒壶"].next_time,
        fail_delay: taskConfig["领取饭盒酒壶"].fail_delay,
      },
      "每日一抽": {
        enabled: taskConfig["每日一抽"].enabled,
        next_time: taskConfig["每日一抽"].next_time,
        fail_delay: taskConfig["每日一抽"].fail_delay,
      },
      "御魂": {
        enabled: taskConfig["御魂"].enabled,
        run_count: taskConfig["御魂"].run_count,
        remaining_count: taskConfig["御魂"].remaining_count,
        unlocked_count: taskConfig["御魂"].unlocked_count,
        target_level: taskConfig["御魂"].target_level,
        fail_delay: taskConfig["御魂"].fail_delay,
      },
      "加好友": {
        enabled: taskConfig["加好友"].enabled,
        next_time: taskConfig["加好友"].next_time,
        fail_delay: taskConfig["加好友"].fail_delay,
      },
      "每周分享": {
        enabled: taskConfig["每周分享"].enabled,
        next_time: taskConfig["每周分享"].next_time,
        fail_delay: taskConfig["每周分享"].fail_delay,
      },
      "召唤礼包": {
        enabled: taskConfig["召唤礼包"].enabled,
        next_time: taskConfig["召唤礼包"].next_time,
        fail_delay: taskConfig["召唤礼包"].fail_delay,
      },
      "斗技": {
        enabled: taskConfig["斗技"].enabled,
        start_hour: taskConfig["斗技"].start_hour,
        end_hour: taskConfig["斗技"].end_hour,
        mode: taskConfig["斗技"].mode,
        target_score: taskConfig["斗技"].target_score,
        next_time: taskConfig["斗技"].next_time,
        fail_delay: taskConfig["斗技"].fail_delay,
      },
      "对弈竞猜": {
        enabled: taskConfig["对弈竞猜"].enabled,
        next_time: taskConfig["对弈竞猜"].next_time,
        fail_delay: taskConfig["对弈竞猜"].fail_delay,
      }
    }

    if (isInit) {
      // 起号专属任务
      configToSend["起号_领取奖励"] = {
        enabled: taskConfig["起号_领取奖励"].enabled,
        next_time: taskConfig["起号_领取奖励"].next_time,
        fail_delay: taskConfig["起号_领取奖励"].fail_delay,
      }
      configToSend["起号_租借式神"] = {
        enabled: taskConfig["起号_租借式神"].enabled,
        next_time: taskConfig["起号_租借式神"].next_time,
        fail_delay: taskConfig["起号_租借式神"].fail_delay,
      }
      configToSend["起号_新手任务"] = {
        enabled: taskConfig["起号_新手任务"].enabled,
        next_time: taskConfig["起号_新手任务"].next_time,
        fail_delay: taskConfig["起号_新手任务"].fail_delay,
      }
      configToSend["起号_经验副本"] = {
        enabled: taskConfig["起号_经验副本"].enabled,
        next_time: taskConfig["起号_经验副本"].next_time,
        fail_delay: taskConfig["起号_经验副本"].fail_delay,
      }
      configToSend["起号_领取锦囊"] = {
        enabled: taskConfig["起号_领取锦囊"].enabled,
        next_time: taskConfig["起号_领取锦囊"].next_time,
        fail_delay: taskConfig["起号_领取锦囊"].fail_delay,
      }
      configToSend["起号_式神养成"] = {
        enabled: taskConfig["起号_式神养成"].enabled,
        next_time: taskConfig["起号_式神养成"].next_time,
        fail_delay: taskConfig["起号_式神养成"].fail_delay,
      }
      configToSend["起号_升级饭盒"] = {
        enabled: taskConfig["起号_升级饭盒"].enabled,
        next_time: taskConfig["起号_升级饭盒"].next_time,
        fail_delay: taskConfig["起号_升级饭盒"].fail_delay,
      }
      configToSend["领取成就奖励"] = {
        enabled: taskConfig["领取成就奖励"].enabled,
        next_time: taskConfig["领取成就奖励"].next_time,
        fail_delay: taskConfig["领取成就奖励"].fail_delay,
      }
      configToSend["弥助"] = {
        enabled: taskConfig["弥助"].enabled,
        next_time: taskConfig["弥助"].next_time,
        fail_delay: taskConfig["弥助"].fail_delay,
      }
      configToSend["爬塔"] = {
        enabled: taskConfig["爬塔"].enabled,
        next_time: taskConfig["爬塔"].next_time,
        fail_delay: taskConfig["爬塔"].fail_delay,
      }
    } else {
      // 正常专属任务
      configToSend["寄养"] = {
        enabled: taskConfig["寄养"].enabled,
        next_time: taskConfig["寄养"].next_time,
        fail_delay: taskConfig["寄养"].fail_delay,
      }
      configToSend["悬赏"] = {
        enabled: taskConfig["悬赏"].enabled,
        next_time: taskConfig["悬赏"].next_time,
        fail_delay: taskConfig["悬赏"].fail_delay,
      }
      configToSend["弥助"] = {
        enabled: taskConfig["弥助"].enabled,
        next_time: taskConfig["弥助"].next_time,
        fail_delay: taskConfig["弥助"].fail_delay,
      }
      configToSend["勾协"] = {
        enabled: taskConfig["勾协"].enabled,
        next_time: taskConfig["勾协"].next_time,
        fail_delay: taskConfig["勾协"].fail_delay,
      }
      configToSend["结界卡合成"] = {
        enabled: taskConfig["结界卡合成"].enabled,
        explore_count: taskConfig["结界卡合成"].explore_count
      }
      configToSend["爬塔"] = {
        enabled: taskConfig["爬塔"].enabled,
        next_time: taskConfig["爬塔"].next_time,
        fail_delay: taskConfig["爬塔"].fail_delay,
      }
      configToSend["逢魔"] = {
        enabled: taskConfig["逢魔"].enabled,
        next_time: taskConfig["逢魔"].next_time,
        fail_delay: taskConfig["逢魔"].fail_delay,
      }
      configToSend["道馆"] = {
        enabled: taskConfig["道馆"].enabled,
        next_time: taskConfig["道馆"].next_time,
        fail_delay: taskConfig["道馆"].fail_delay,
      }
      configToSend["秘闻"] = {
        enabled: taskConfig["秘闻"].enabled,
        next_time: taskConfig["秘闻"].next_time,
        fail_delay: taskConfig["秘闻"].fail_delay,
      }
    }

    const response = await updateTaskConfig(selectedAccount.value.id, configToSend)
    const mergedConfig = response?.config || configToSend

    selectedAccount.value.task_config = mergedConfig

    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.task_config = mergedConfig
          break
        }
      }
    }
    updateAccountInTree(accountTree.value)

    if (response?.message && response.message.includes('未变更')) {
      ElMessage.warning(response.message)
    } else {
      ElMessage.success(response?.message || '任务配置已更新')
    }
  } catch (error) {
    ElMessage.error('更新失败')
  }
}
const updateRestConfigData = async () => {
  if (!selectedAccount.value) return

  try {
    await updateRestConfig(selectedAccount.value.id, {
      enabled: restConfig.enabled,
      mode: restConfig.mode,
      start_time: restConfig.start_time,
      duration: restConfig.duration
    })

    // 禁用时清空休息计划
    if (!restConfig.enabled) {
      restPlan.value = {}
    } else {
      // 刷新休息计划
      try {
        const plan = await getRestPlan(selectedAccount.value.id)
        restPlan.value = plan
      } catch (error) {
        restPlan.value = {}
      }
    }

    // 同步到账号树
    const updateInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.rest_config = {
            enabled: restConfig.enabled,
            mode: restConfig.mode,
            start_time: restConfig.start_time,
            duration: restConfig.duration
          }
          break
        }
      }
    }
    updateInTree(accountTree.value)

    ElMessage.success('休息配置已更新')
  } catch (error) {
    ElMessage.error('更新失败')
  }
}

// 显示添加游戏对话框
const showAddGameDialog = () => {
  gameForm.login_id = ''
  gameForm.level = 1
  gameForm.stamina = 0
  gameDialogVisible.value = true
}

// 添加游戏账号
const handleAddGame = async () => {
  if (!gameForm.login_id) {
    ElMessage.warning('请填写完整信息')
    return
  }

  try {
    await createGameAccount(gameForm)
    ElMessage.success('游戏账号添加成功')
    gameDialogVisible.value = false
    fetchAccounts()
  } catch (error) {
    ElMessage.error('添加失败')
  }
}

// 获取状态类型
const getStatusType = (status) => {
  if (status === 1) return 'success'
  if (status === 3) return 'warning'
  return 'danger'
}

// 获取状态文本
const getStatusText = (status) => {
  if (status === 1) return '正常'
  if (status === 3) return '藏宝阁'
  return '失效'
}

// 删除游戏账号
const handleDeleteGame = async (id) => {
  try {
    await deleteGameAccount(id)
    ElMessage.success('账号已删除')
    if (selectedAccount.value && selectedAccount.value.id === id) {
      selectedAccount.value = null
      restPlan.value = {}
    }
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 阵容配置
const openLineupDialog = async () => {
  if (!selectedAccount.value) return
  try {
    const config = await getLineupConfig(selectedAccount.value.id)
    lineupTableData.value = LINEUP_TASKS.map(task => ({
      task,
      group: config[task]?.group ?? 1,
      position: config[task]?.position ?? 1
    }))
  } catch {
    lineupTableData.value = LINEUP_TASKS.map(task => ({
      task, group: 1, position: 1
    }))
  }
  lineupDialogVisible.value = true
}

const saveLineupConfig = async () => {
  if (!selectedAccount.value) return
  try {
    const data = {}
    for (const row of lineupTableData.value) {
      data[row.task] = { group: row.group, position: row.position }
    }
    await updateLineupConfig(selectedAccount.value.id, data)
    ElMessage.success('阵容配置已保存')
    lineupDialogVisible.value = false
  } catch {
    ElMessage.error('保存阵容配置失败')
  }
}

// 更新式神状态配置
const updateShikigamiData = async () => {
  if (!selectedAccount.value) return

  try {
    const data = {
      "座敷童子": { ...shikigamiConfig.座敷童子 }
    }
    const response = await updateShikigamiConfig(selectedAccount.value.id, data)
    ElMessage.success(response?.message || '式神配置已更新')

    // 同步到账号树
    if (response?.config) {
      selectedAccount.value.shikigami_config = response.config
      const updateInTree = (nodes) => {
        for (const node of nodes) {
          if (node.type === 'game' && node.id === selectedAccount.value.id) {
            node.shikigami_config = response.config
            break
          }
        }
      }
      updateInTree(accountTree.value)
    }
  } catch {
    ElMessage.error('更新式神配置失败')
  }
}

onMounted(() => {
  fetchAccounts()
  // 加载全局休息开关状态
  apiRequest(API_ENDPOINTS.system.globalRest)
    .then(resp => resp.json())
    .then(data => { globalRestEnabled.value = data.enabled ?? true })
    .catch(() => {})
})
</script>

<style scoped lang="scss">
.accounts {
  .action-bar {
    margin-bottom: 20px;
  }

  .account-tree {
    height: calc(100vh - 200px);
    overflow: auto;

    .tree-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .tree-node {
      display: flex;
      align-items: center;
      gap: 5px;

      .status-tag {
        margin-left: auto;
      }

      .remark-tag {
        margin-left: 4px;
        max-width: 80px;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }

  .account-detail {
    height: calc(100vh - 200px);
    overflow: auto;

    .config-item {
      margin-left: 20px;
      color: #606266;
    }

    .rest-plan {
      padding: 10px 0;
    }
  }
}
</style>
