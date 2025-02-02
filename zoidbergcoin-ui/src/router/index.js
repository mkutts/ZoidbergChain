import { createRouter, createWebHistory } from 'vue-router';
import HomePage from '../pages/HomePage.vue';
import Dashboard from '../pages/Dashboard.vue';
import Blockchain from '../pages/Blockchain.vue';

const routes = [
  { path: '/', component: HomePage },
  { path: '/dashboard', component: Dashboard },
  { path: '/blockchain', component: Blockchain },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
