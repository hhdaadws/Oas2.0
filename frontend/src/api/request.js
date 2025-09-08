import axios from 'axios'
import { ElMessage } from 'element-plus'

// 鍒涘缓axios瀹炰緥
const service = axios.create({
  baseURL: 'http://127.0.0.1:9001/api',
  timeout: 15000
})

// 璇锋眰鎷︽埅鍣?
service.interceptors.request.use(
  config => {
    // 鍙互鍦ㄨ繖閲屾坊鍔爐oken绛?
    return config
  },
  error => {
    console.error(error)
    return Promise.reject(error)
  }
)

// 鍝嶅簲鎷︽埅鍣?
service.interceptors.response.use(
  response => {
    const res = response.data
    return res
  },
  error => {
    console.error('err' + error)
    ElMessage({ message: (error.response && (error.response.data?.detail || error.response.data?.message || error.response.data?.error)) || error.message,
      type: 'error',
      duration: 5 * 1000
    })
    return Promise.reject(error)
  }
)

export default service
