import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { API_BASE_URL } from '@/config'

const service = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  timeout: 15000
})

const TOKEN_KEY = 'yys_auth_token'
const MODE_KEY = 'yys_auth_mode'
const CLOUD_CRED_KEY = 'yys_cloud_credentials'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(MODE_KEY)
}

export function getMode() {
  return localStorage.getItem(MODE_KEY) || 'local'
}

export function setMode(mode) {
  localStorage.setItem(MODE_KEY, mode)
}

export function getCloudCredentials() {
  try {
    const raw = localStorage.getItem(CLOUD_CRED_KEY)
    if (!raw) return null
    const { username, password } = JSON.parse(raw)
    return username ? { username, password } : null
  } catch {
    return null
  }
}

export function setCloudCredentials(username, password) {
  localStorage.setItem(CLOUD_CRED_KEY, JSON.stringify({ username, password }))
}

export function removeCloudCredentials() {
  localStorage.removeItem(CLOUD_CRED_KEY)
}

// 请求拦截器
service.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    console.error(error)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    if (error.response && error.response.status === 401) {
      removeToken()
      const currentPath = router.currentRoute.value.path
      if (currentPath !== '/login') {
        router.push('/login')
        ElMessage({
          message: '登录已过期，请重新登录',
          type: 'warning',
          duration: 3000
        })
      } else {
        const detail = error.response.data?.detail
        if (detail) {
          ElMessage({
            message: detail,
            type: 'error',
            duration: 5000
          })
        }
      }
      return Promise.reject(error)
    }

    console.error('err' + error)
    ElMessage({
      message: (error.response && (error.response.data?.detail || error.response.data?.message || error.response.data?.error)) || error.message,
      type: 'error',
      duration: 5 * 1000
    })
    return Promise.reject(error)
  }
)

export default service
