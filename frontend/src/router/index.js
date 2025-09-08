import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/views/Layout.vue'

const routes = [
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '仪表盘', icon: 'Monitor' }
      },
      {
        path: 'accounts',
        name: 'Accounts',
        component: () => import('@/views/Accounts.vue'),
        meta: { title: '账号管理', icon: 'User' }
      },
      {
        path: 'coop',
        name: 'Coop',
        component: () => import('@/views/Coop.vue'),
        meta: { title: '勾协管理', icon: 'Connection' }
      },
      {
        path: 'emulators',
        name: 'Emulators',
        component: () => import('@/views/Emulators.vue'),
        meta: { title: '模拟器配置', icon: 'Monitor' }
      },
      {
        path: 'config',
        name: 'Config', 
        component: () => import('@/views/Config.vue'),
        meta: { title: '系统配置', icon: 'Setting' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router