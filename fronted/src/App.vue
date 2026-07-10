<!-- frontend/src/App.vue -->
<template>
  <div id="app">
    <ChatWindow />
  </div>
</template>

<script setup>
import ChatWindow from './components/ChatWindow.vue';
</script>

<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  margin: 0;
  padding: 0;
  background-color: #f0f2f5;
}
#app {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}
</style>
