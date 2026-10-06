<script setup lang="ts">
import { Plus,MessageSquareText,Trash2 } from '@lucide/vue';import { useRouter } from 'vue-router';import { useAppStore } from '../stores/app'
const app=useAppStore(),router=useRouter();
/** 创建并导航到一个新的聊天会话。 */
async function create(){const s=await app.createSession();router.push(`/chat/${s.session_id}`)}
/** 切换会话数据并更新浏览器路由。 */
async function select(id:string){await app.selectSession(id);router.push(`/chat/${id}`)}
</script>
<template><aside class="session-sidebar"><div class="section-heading"><div><span class="eyebrow">CONVERSATIONS</span><h2>旅程会话</h2></div><button class="icon-button accent" aria-label="新建会话" @click="create"><Plus :size="18"/></button></div><div class="session-list"><button v-for="session in app.sessions" :key="session.session_id" class="session-row" :class="{active:app.activeSessionId===session.session_id}" @click="select(session.session_id)"><MessageSquareText :size="17"/><span><strong>{{session.title||'未命名旅程'}}</strong><small>{{session.current_trip_id?'已有行程':'等待灵感'}}</small></span><i class="delete-session" role="button" @click.stop="app.removeSession(session.session_id)"><Trash2 :size="14"/></i></button></div></aside></template>
