<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import AppShell from './components/AppShell.vue'
import { useAppStore } from './stores/app'

const app = useAppStore()
onMounted(() => app.bootstrap())
</script>

<template><AppShell><RouterView /></AppShell></template>
