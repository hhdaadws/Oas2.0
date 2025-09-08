import request from './request'

// 获取任务队列
export function getTaskQueue() {
  return request({
    url: '/tasks/queue',
    method: 'get'
  })
}

// 获取执行历史
export function getTaskHistory(params) {
  return request({
    url: '/tasks/history',
    method: 'get',
    params
  })
}

// 获取任务统计
export function getTaskStats() {
  return request({
    url: '/tasks/stats',
    method: 'get'
  })
}