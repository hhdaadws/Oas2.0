import request from './request'

export function login(code) {
  return request({
    url: '/auth/login',
    method: 'post',
    data: { code }
  })
}

export function checkAuthStatus() {
  return request({
    url: '/auth/status',
    method: 'get'
  })
}
