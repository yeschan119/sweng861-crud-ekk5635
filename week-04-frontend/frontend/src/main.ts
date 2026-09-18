import './assets/main.css'

import { createApp } from 'vue'
import { createWebHistory } from 'vue-router'
import App from './App.vue'
import { createAppRouter } from './router'

const app = createApp(App)

app.use(createAppRouter(createWebHistory(import.meta.env.BASE_URL)))

app.mount('#app')
