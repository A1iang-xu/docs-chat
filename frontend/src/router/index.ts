import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', name: 'Chat', component: () => import('@/views/ChatView.vue') },
  { path: '/knowledge', name: 'KnowledgeBase', component: () => import('@/views/KnowledgeBaseView.vue') },
  { path: '/evaluation', name: 'Evaluation', component: () => import('@/views/EvaluationView.vue') },
  { path: '/dashboard', name: 'Dashboard', component: () => import('@/views/DashboardView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})