import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const service = axios.create({
  baseURL: 'http://127.0.0.1:9001/api',
  timeout: 15000
})

const TOKEN_KEY = 'yys_auth_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
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
