import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: {
      title: '运行总览',
      desc: '系统状态、模型信息与报警统计一览',
      nav: '总览',
    },
  },
  {
    path: '/live',
    name: 'live',
    component: () => import('../views/LiveView.vue'),
    meta: {
      title: '实时检测',
      desc: '调用本机摄像头，逐帧推理并叠加检测框',
      nav: '实时检测',
    },
  },
  {
    path: '/image',
    name: 'image',
    component: () => import('../views/ImageView.vue'),
    meta: {
      title: '图片检测',
      desc: '上传单张图片，查看检测框、置信度与告警',
      nav: '图片检测',
    },
  },
  {
    path: '/video',
    name: 'video',
    component: () => import('../views/VideoView.vue'),
    meta: {
      title: '视频检测',
      desc: '离线逐帧检测视频文件，输出标注后的视频',
      nav: '视频检测',
    },
  },
  {
    path: '/events',
    name: 'events',
    component: () => import('../views/EventsView.vue'),
    meta: {
      title: '报警记录',
      desc: '按级别 / 来源 / 类别筛选历史报警与快照',
      nav: '报警记录',
    },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
    meta: {
      title: '参数设置',
      desc: '模型切换、推理阈值与告警策略',
      nav: '参数设置',
    },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} · 火灾烟雾智能识别系统` : '火灾烟雾智能识别系统'
})

export default router
