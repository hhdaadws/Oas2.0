<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside width="200px" class="layout-aside">
      <div class="logo">
        <h3>阴阳师调度系统</h3>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item
          v-for="route in menuRoutes"
          :key="route.path"
          :index="route.path"
        >
          <el-icon>
            <component :is="route.meta.icon" />
          </el-icon>
          <span>{{ route.meta.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主体区域 -->
    <el-container>
      <!-- 顶部栏 -->
      <el-header class="layout-header">
        <div class="header-left">
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="header-right">
          <span class="time">{{ currentTime }}</span>
        </div>
      </el-header>

      <!-- 内容区域 -->
      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'

const route = useRoute()

// 菜单路由
const menuRoutes = [
  { path: '/dashboard', meta: { title: '仪表盘', icon: 'Monitor' } },
  { path: '/accounts', meta: { title: '账号管理', icon: 'User' } },
  { path: '/coop', meta: { title: '勾协管理', icon: 'Connection' } },
  { path: '/emulators', meta: { title: '模拟器配置', icon: 'Monitor' } },
  { path: '/account-pull', meta: { title: '账号抓取', icon: 'Download' } },
  { path: '/settings', meta: { title: '系统配置', icon: 'Setting' } }
]

// 当前激活菜单
const activeMenu = computed(() => route.path)

// 当前页面标题
const currentTitle = computed(() => {
  const current = menuRoutes.find(r => r.path === route.path)
  return current ? current.meta.title : '仪表盘'
})

// 当前时间
const currentTime = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
let timer = null

onMounted(() => {
  timer = setInterval(() => {
    currentTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped lang="scss">
.layout-container {
  height: 100%;
}

.layout-aside {
  background-color: #304156;

  .logo {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #2b2f3a;

    h3 {
      color: #fff;
      margin: 0;
      font-size: 16px;
    }
  }

  .el-menu {
    border-right: none;
  }
}

.layout-header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;

  .header-left {
    h2 {
      margin: 0;
      font-size: 18px;
      color: #303133;
    }
  }

  .header-right {
    .time {
      color: #606266;
      font-size: 14px;
    }
  }
}

.layout-main {
  background-color: #f5f7fa;
  padding: 20px;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
