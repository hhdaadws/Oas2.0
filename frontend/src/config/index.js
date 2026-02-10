/**
 * 全局API配置
 */

// API基础地址（统一指向本机）
export const API_BASE_URL = 'http://127.0.0.1:9001'

// API端点配置
export const API_ENDPOINTS = {
  // 账号相关
  accounts: '/api/accounts',
  accountUpdate: (id) => `/api/accounts/${id}`,
  taskConfig: (id) => `/api/accounts/${id}/task-config`,
  restConfig: (id) => `/api/accounts/${id}/rest-config`,
  restPlan: (id) => `/api/accounts/${id}/rest-plan`,
  lineupConfig: (id) => `/api/accounts/${id}/lineup-config`,

  // 仪表盘相关
  dashboard: '/api/dashboard',
  realtimeStats: '/api/stats/realtime',

  // 任务相关
  tasks: {
    queue: '/api/tasks/queue',
    history: '/api/tasks/history',
    stats: '/api/tasks/stats',
    logs: '/api/tasks/logs',
    runtimeLogs: '/api/tasks/runtime-logs',
    scheduler: {
      status: '/api/tasks/scheduler/status',
      start: '/api/tasks/scheduler/start',
      stop: '/api/tasks/scheduler/stop'
    }
  },

  // 执行引擎
  executor: {
    queue: '/api/executor/queue',
    running: '/api/executor/running',
    metrics: '/api/executor/metrics'
  },

  // 模拟器相关
  emulators: '/api/emulators/',
  emulatorUpdate: (id) => `/api/emulators/${id}`,
  emulatorDelete: (id) => `/api/emulators/${id}`,
  emulatorScreenshot: (id) => `/api/emulators/${id}/screenshot`,
  emulatorClick: (id) => `/api/emulators/${id}/click`,
  emulatorConnectAll: '/api/emulators/connect',
  emulatorRefresh: '/api/emulators/refresh',
  emulatorLaunch: (id) => `/api/emulators/${id}/launch`,
  emulatorOcr: (id) => `/api/emulators/${id}/ocr`,

  // 系统设置
  system: {
    settings: '/api/system/settings',
    captureBenchmark: '/api/system/capture/benchmark'
  }
}

/**
 * 构建完整的API URL
 * @param {string} endpoint - API端点
 * @returns {string} 完整的URL
 */
export const buildApiUrl = (endpoint) => {
  return `${API_BASE_URL}${endpoint}`
}

/**
 * API请求封装
 * @param {string} endpoint - API端点
 * @param {object} options - fetch选项
 * @returns {Promise} fetch响应
 */
export const apiRequest = async (endpoint, options = {}) => {
  const url = buildApiUrl(endpoint)
  const token = localStorage.getItem('yys_auth_token')
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...options.headers
    }
  }

  return fetch(url, { ...defaultOptions, ...options })
}
