import { createRouter, createWebHistory } from 'vue-router';
import HomePage from '../pages/HomePage.vue';
import Dashboard from '../pages/Dashboard.vue';
import Blockchain from '../pages/Blockchain.vue';
import WhyZoidbergCoin from '../pages/WhyZoidbergCoin.vue';

const routes = [
  { path: '/', component: HomePage },
  { path: '/dashboard', component: Dashboard },
  { path: '/blockchain', component: Blockchain },
  { path: '/why-zoidbergcoin', component: WhyZoidbergCoin }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
