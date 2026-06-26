import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'highlight.js/styles/github-dark.css'
import './assets/themes.css'  // v4.5: 亮色主题
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.mount('#app')