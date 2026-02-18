import request from './request'

export function login(payload) {
  return request({
    url: '/auth/login',
    method: 'post',
    data: payload
  })
}

export function checkAuthStatus() {
  return request({
    url: '/auth/status',
    method: 'get'
  })
}
