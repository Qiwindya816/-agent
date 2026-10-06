import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import ChatView from './views/ChatView.vue'
import TripsView from './views/TripsView.vue'
import MemoryView from './views/MemoryView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import SettingsView from './views/SettingsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: DashboardView, meta: { title: '旅行工作台' } },
    { path: '/chat/:sessionId?', component: ChatView, meta: { title: '和 TravelMind 对话' } },
    { path: '/trips', component: TripsView, meta: { title: '行程规划' } },
    { path: '/memory', component: MemoryView, meta: { title: '旅行记忆' } },
    { path: '/knowledge', component: KnowledgeView, meta: { title: '知识库' } },
    { path: '/settings', component: SettingsView, meta: { title: '设置' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
