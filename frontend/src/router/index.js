import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/views/Layout.vue'
import { getToken } from '@/api/request'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
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
        path: 'emulators/test',
        name: 'EmulatorTest',
        component: () => import('@/views/EmulatorTest.vue'),
        meta: { title: '模拟器测试', icon: 'Monitor' }
      },
      {
        path: 'account-pull',
        name: 'AccountPull',
        component: () => import('@/views/AccountPull.vue'),
        meta: { title: '账号抓取', icon: 'Download' }
      },
      {
        path: 'settings',
        name: 'SystemConfig',
        component: () => import('@/views/SystemConfig.vue'),
        meta: { title: '系统配置', icon: 'Setting' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：未登录跳转到登录页
router.beforeEach((to, from, next) => {
  if (to.meta.public) {
    if (to.path === '/login' && getToken()) {
      next('/dashboard')
    } else {
      next()
    }
    return
  }

  if (!getToken()) {
    next('/login')
    return
  }

  next()
})

export default router
