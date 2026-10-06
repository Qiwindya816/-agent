<script setup lang="ts">
import { computed,onMounted,ref,watch } from 'vue'
import { CalendarDays,ChevronDown,MapPin,Footprints,WalletCards,History,Pencil,Save,X,CloudSun,LoaderCircle,MapPinned } from '@lucide/vue'
import { api } from '../services/api'
import { useAppStore } from '../stores/app'
import MapCanvas from '../components/MapCanvas.vue'
import EmptyState from '../components/EmptyState.vue'
import type { Activity,TripVersion,WeatherForecast } from '../types'

const app=useAppStore()
const versions=ref<TripVersion[]>([])
const selectedVersion=ref<TripVersion|null>(null)
const selectedDay=ref(1)
const editing=ref<Activity|null>(null)
const draft=ref({name:'',start_time:'',end_time:'',notes:''})
const weather=ref<WeatherForecast|null>(null)
const weatherLoading=ref(false)
const mapLoading=ref(false)
const trip=computed(()=>app.activeTrip)
const itinerary=computed(()=>selectedVersion.value?.itinerary||null)
const coordinateCount=computed(()=>(itinerary.value?.days||[]).flatMap(day=>day.activities).filter(activity=>activity.poi?.location).length)

/** 加载当前会话、旅行版本和默认选中的最新行程。 */
async function load(){
  if(!app.sessions.length)await app.loadSessions().catch(()=>undefined)
  if(!app.activeSessionId)return
  await app.selectSession(app.activeSessionId)
  if(!trip.value)return
  versions.value=await api.tripVersions(trip.value.trip_id,trip.value.session_id)
  selectedVersion.value=versions.value.at(-1)||null
  weather.value=null
}

/** 将指定活动复制到编辑表单。 */
function edit(activity:Activity){
  editing.value=activity
  draft.value={name:activity.name,start_time:activity.start_time||'',end_time:activity.end_time||'',notes:activity.notes||''}
}

/** 保存活动修改，并把后端返回结果追加为新的行程版本。 */
async function save(){
  if(!trip.value||!editing.value)return
  const result:any=await api.editActivity(trip.value.trip_id,trip.value.session_id,{action:'update',activity_id:editing.value.activity_id,...draft.value})
  versions.value.push({version_id:result.version_id,version_number:result.version_number,trip_id:trip.value.trip_id,user_id:app.userId,itinerary:result.itinerary,change_reason:result.change_reason,source_agent:'frontend_edit',created_at:new Date().toISOString()})
  selectedVersion.value=versions.value.at(-1)||null
  editing.value=null
  app.showNotice('活动已更新，并保存为新版本')
}

/** 调用后端地图增强接口，为行程地点补齐坐标。 */
async function enrichMap(){
  if(!trip.value||mapLoading.value)return
  mapLoading.value=true
  try{
    const result=await api.enrichTripMap(trip.value.trip_id,trip.value.session_id)
    versions.value.push({version_id:result.version_id,version_number:result.version_number,trip_id:trip.value.trip_id,user_id:app.userId,itinerary:result.itinerary,change_reason:result.change_reason,source_agent:'map_enrichment',created_at:new Date().toISOString()})
    selectedVersion.value=versions.value.at(-1)||null
    app.showNotice(`已补全 ${result.resolved_activities} 个地点坐标`)
  }catch(error){
    app.showNotice(error instanceof Error?error.message:'地图坐标补全失败')
  }finally{
    mapLoading.value=false
  }
}

/** 调用天气工具并显示当前目的地的结构化预报。 */
async function loadWeather(){
  if(!trip.value||!itinerary.value?.destination||weatherLoading.value)return
  weatherLoading.value=true
  try{
    const result=await api.invokeTool('check_weather',{location:itinerary.value.destination,days:itinerary.value.travel_days||7},trip.value.session_id,trip.value.trip_id)
    if(!result.success)throw new Error(result.error?.message||'天气查询失败')
    weather.value=(result.metadata?.forecast||null) as WeatherForecast|null
    if(!weather.value)throw new Error('天气服务没有返回结构化预报')
  }catch(error){
    app.showNotice(error instanceof Error?error.message:'天气查询失败')
  }finally{
    weatherLoading.value=false
  }
}

onMounted(load)
watch(()=>app.activeSessionId,load)
</script>

<template>
  <div v-if="itinerary" class="trip-workspace">
    <section class="trip-toolbar paper-card">
      <div><span class="eyebrow">ITINERARY BOOK</span><h2>{{itinerary.title||`${itinerary.destination}之旅`}}</h2><p>{{itinerary.departure_city||'出发地待定'}} → {{itinerary.destination}}</p></div>
      <div class="toolbar-metrics"><span><CalendarDays :size="16"/>{{itinerary.travel_days}} 天</span><span><WalletCards :size="16"/>¥{{itinerary.total_estimated_cost?.toLocaleString()||'—'}}</span><label><History :size="16"/><select v-model="selectedVersion"><option v-for="version in versions" :key="version.version_id" :value="version">版本 {{version.version_number}} · {{version.change_reason||'初始方案'}}</option></select><ChevronDown :size="14"/></label></div>
    </section>
    <section class="map-section paper-card">
      <MapCanvas :itinerary="itinerary" :selected-day="selectedDay"/>
      <div v-if="!coordinateCount" class="map-enrichment-bar"><span><MapPinned :size="16"/>当前行程还没有经过地图坐标校验</span><button class="button secondary" :disabled="mapLoading" @click="enrichMap"><LoaderCircle v-if="mapLoading" :size="14" class="spin"/>{{mapLoading?'正在连接高德…':'补全地图坐标'}}</button></div>
      <div class="day-tabs"><button v-for="day in itinerary.days" :key="day.day" :class="{active:selectedDay===day.day}" @click="selectedDay=day.day"><b>D{{day.day}}</b><span>{{day.theme||`第 ${day.day} 天`}}</span></button></div>
    </section>
    <section class="timeline-section paper-card">
      <div class="section-heading"><div><span class="eyebrow">DAY {{String(selectedDay).padStart(2,'0')}}</span><h2>{{itinerary.days.find(d=>d.day===selectedDay)?.theme||'今日安排'}}</h2></div><button class="weather-chip weather-button" :disabled="weatherLoading" @click="loadWeather"><LoaderCircle v-if="weatherLoading" :size="17" class="spin"/><CloudSun v-else :size="17"/>{{weatherLoading?'查询中…':weather?'刷新天气':'查看天气'}}</button></div>
      <div v-if="weather" class="weather-panel"><div><strong>{{weather.location}}</strong><small>{{weather.source}} · 未来 {{weather.days.length}} 天</small></div><div class="weather-days"><article v-for="day in weather.days" :key="day.date"><b>{{day.date.slice(5)}}</b><span>{{day.weather}}</span><small>{{day.min_temperature??'—'}}~{{day.max_temperature??'—'}}℃</small><small>降水 {{day.precipitation_sum??'—'}} mm</small></article></div></div>
      <div class="activity-timeline"><article v-for="(activity,index) in itinerary.days.find(d=>d.day===selectedDay)?.activities" :key="activity.activity_id"><div class="time-col"><strong>{{activity.start_time||'待定'}}</strong><span>{{activity.end_time||''}}</span></div><div class="timeline-mark"><i>{{index+1}}</i></div><div class="activity-card"><div><span class="activity-type">{{activity.category||'行程活动'}}</span><h3>{{activity.name}}</h3><p><MapPin :size="14"/>{{activity.location||activity.poi?.address||'地点待确认'}}</p></div><div class="activity-meta"><span v-if="activity.estimated_cost!==undefined">¥{{activity.estimated_cost}}</span><span v-if="activity.transport_method"><Footprints :size="14"/>{{activity.transport_method}}</span><button class="icon-button" aria-label="编辑活动" @click="edit(activity)"><Pencil :size="16"/></button></div><small v-if="activity.notes" class="activity-note">{{activity.notes}}</small></div></article></div>
    </section>
    <div v-if="editing" class="modal-backdrop" @click.self="editing=null"><form class="modal-card" @submit.prevent="save"><div class="section-heading"><div><span class="eyebrow">EDIT ACTIVITY</span><h2>局部调整活动</h2></div><button type="button" class="icon-button" @click="editing=null"><X :size="18"/></button></div><label>活动名称<input v-model="draft.name" required></label><div class="field-row"><label>开始时间<input v-model="draft.start_time" type="time"></label><label>结束时间<input v-model="draft.end_time" type="time"></label></div><label>备注<textarea v-model="draft.notes" rows="3"></textarea></label><button class="button primary" type="submit"><Save :size="17"/>保存为新版本</button></form></div>
  </div>
  <EmptyState v-else title="行程册还是空的" description="完成一段旅行对话后，地图、每日时间轴和历史版本会自动汇集到这里。"><RouterLink to="/chat" class="button primary">去规划第一段旅程</RouterLink></EmptyState>
</template>
