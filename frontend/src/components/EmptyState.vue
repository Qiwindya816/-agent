<script setup lang="ts">import { Compass } from '@lucide/vue';defineProps<{title:string;description:string}>()</script>
<template><div class="empty-state"><span><Compass :size="24"/></span><h3>{{title}}</h3><p>{{description}}</p><slot/></div></template>
