import { createRouter, createWebHistory } from 'vue-router';
import HomePage from '../pages/HomePage.vue';
import Dashboard from '../pages/Dashboard.vue';
import WhyZoidbergCoin from '../pages/WhyZoidbergCoin.vue';
import AdminPage from '../pages/AdminPage.vue';

const routes = [
  { path: '/', component: HomePage },
  { path: '/dashboard', component: Dashboard, meta: { appSection: 'home' } },
  { path: '/submit', component: Dashboard, meta: { appSection: 'submit' } },
  { path: '/vote', component: Dashboard, meta: { appSection: 'vote' } },
  { path: '/rewards', component: Dashboard, meta: { appSection: 'rewards' } },
  { path: '/activity', component: Dashboard, meta: { appSection: 'activity' } },
  { path: '/help', component: Dashboard, meta: { appSection: 'help' } },
  { path: '/feedback', component: Dashboard, meta: { appSection: 'feedback' } },
  { path: '/blockchain', redirect: '/activity' },
  { path: '/why-zoidbergcoin', component: WhyZoidbergCoin, meta: { skipAccessGate: true } },
  { path: '/admin', component: AdminPage, meta: { skipAccessGate: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
