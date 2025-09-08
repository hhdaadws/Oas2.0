import request from './request'

// 获取仪表盘数据
export function getDashboard() {
  return request({
    url: '/dashboard',
    method: 'get'
  })
}

// 获取实时统计
export function getRealtimeStats() {
  return request({
    url: '/stats/realtime',
    method: 'get'
  })
}