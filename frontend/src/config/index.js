/**
 * 全局API配置
 */

// API基础地址
export const API_BASE_URL = 'http://113.45.64.80:9001'

// API端点配置
export const API_ENDPOINTS = {
  // 账号相关
  accounts: '/api/accounts',
  accountUpdate: (id) => `/api/accounts/${id}`,
  taskConfig: (id) => `/api/accounts/${id}/task-config`,
  restConfig: (id) => `/api/accounts/${id}/rest-config`,
  restPlan: (id) => `/api/accounts/${id}/rest-plan`,
  
  // 仪表盘相关
  dashboard: '/api/dashboard',
  realtimeStats: '/api/stats/realtime',
  
  // 任务相关
  tasks: {
    queue: '/api/tasks/queue',
    history: '/api/tasks/history',
    stats: '/api/tasks/stats',
    logs: '/api/tasks/logs',
    scheduler: {
      status: '/api/tasks/scheduler/status',
      start: '/api/tasks/scheduler/start',
      stop: '/api/tasks/scheduler/stop'
    }
  },
  
  // 模拟器相关
  emulators: '/api/emulators/',
  emulatorUpdate: (id) => `/api/emulators/${id}`,
  emulatorDelete: (id) => `/api/emulators/${id}`
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
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  }
  
  return fetch(url, { ...defaultOptions, ...options })
}