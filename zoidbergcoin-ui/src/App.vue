<template>
  <div id="app">
    <router-view />
  </div>
</template>

<style>
/* Reset default browser styles */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  width: 100%;
  background: #000; /* Matches the HomePage theme */
  overflow-x: hidden; /* Prevent horizontal scrollbars */
}

/* Ensure the app container spans the full viewport */
#app {
  height: 100%;
  width: 100%;
}

/* Optional styles for navigation if needed */
nav {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}
</style>
