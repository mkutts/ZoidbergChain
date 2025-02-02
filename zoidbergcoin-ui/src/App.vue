<template>
  <div id="app">
    <nav>
      <router-link to="/">Home</router-link>
      <router-link to="/dashboard">Dashboard</router-link>
      <router-link to="/blockchain">Blockchain</router-link>
    </nav>
    <router-view />
  </div>
</template>

<style>
nav {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}
</style>
