import request from './request'

// 获取账号列表
export function getAccounts() {
  return request({
    url: '/accounts',
    method: 'get'
  })
}

// 添加游戏账号
export function createGameAccount(data) {
  return request({
    url: '/accounts/game',
    method: 'post',
    data
  })
}

// 更新账号信息
export function updateAccount(id, data) {
  return request({
    url: `/accounts/${id}`,
    method: 'put',
    data
  })
}

// 更新任务配置
export function updateTaskConfig(id, data) {
  return request({
    url: `/accounts/${id}/task-config`,
    method: 'put',
    data
  })
}

// 获取休息配置
export function getRestConfig(id) {
  return request({
    url: `/accounts/${id}/rest-config`,
    method: 'get'
  })
}

// 更新休息配置
export function updateRestConfig(id, data) {
  return request({
    url: `/accounts/${id}/rest-config`,
    method: 'put',
    data
  })
}

// 获取休息计划
export function getRestPlan(id) {
  return request({
    url: `/accounts/${id}/rest-plan`,
    method: 'get'
  })
}

// 删除游戏账号（ID账号）
export function deleteGameAccount(id) {
  return request({
    url: `/accounts/${id}`,
    method: 'delete'
  })
}

// 批量删除游戏账号
export function deleteGameAccounts(ids) {
  return request({
    url: '/accounts/batch-delete',
    method: 'post',
    data: { ids }
  })
}

// 获取阵容分组配置
export function getLineupConfig(id) {
  return request({
    url: `/accounts/${id}/lineup-config`,
    method: 'get'
  })
}

// 更新阵容分组配置
export function updateLineupConfig(id, data) {
  return request({
    url: `/accounts/${id}/lineup-config`,
    method: 'put',
    data
  })
}

// 获取式神状态配置
export function getShikigamiConfig(id) {
  return request({
    url: `/accounts/${id}/shikigami-config`,
    method: 'get'
  })
}

// 更新式神状态配置
export function updateShikigamiConfig(id, data) {
  return request({
    url: `/accounts/${id}/shikigami-config`,
    method: 'put',
    data
  })
}

// 获取账号任务执行日志
export function getAccountLogs(id, params = {}) {
  return request({
    url: `/accounts/${id}/logs`,
    method: 'get',
    params
  })
}
