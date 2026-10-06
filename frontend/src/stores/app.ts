import { defineStore } from 'pinia'
import { api } from '../services/api'
import type { MessageItem, SessionItem, TripItem } from '../types'

export const useAppStore=defineStore('app',{
  /** 创建应用级响应式状态，并从浏览器恢复用户和会话标识。 */
  state:()=>({ userId:localStorage.getItem('travelmind_user_id')||'demo_traveler', sessions:[] as SessionItem[], activeSessionId:localStorage.getItem('travelmind_session_id')||'', messages:[] as MessageItem[], trips:[] as TripItem[], loading:false, backendOnline:false, notice:'' }),
  /** 提供当前会话和当前旅行两个派生状态。 */
  getters:{ activeSession:(s)=>s.sessions.find(x=>x.session_id===s.activeSessionId), activeTrip:(s)=>s.trips.find(x=>x.trip_id===s.sessions.find(y=>y.session_id===s.activeSessionId)?.current_trip_id)||s.trips.at(-1) },
  actions:{
    /** 检查后端健康状态并加载初始会话列表。 */
    async bootstrap(){this.loading=true;try{const h=await api.health();this.backendOnline=h.database;await this.loadSessions()}catch{this.backendOnline=false}finally{this.loading=false}},
    /** 获取会话列表并恢复一个仍然有效的当前会话。 */
    async loadSessions(){this.sessions=await api.sessions();if(!this.activeSessionId||!this.sessions.some(x=>x.session_id===this.activeSessionId))this.activeSessionId=this.sessions[0]?.session_id||'';if(this.activeSessionId)localStorage.setItem('travelmind_session_id',this.activeSessionId)},
    /** 切换当前会话并并行加载消息与旅行数据。 */
    async selectSession(id:string){this.activeSessionId=id;localStorage.setItem('travelmind_session_id',id);[this.messages,this.trips]=await Promise.all([api.messages(id),api.trips(id)])},
    /** 创建新会话、加入列表并立即选中。 */
    async createSession(title='新的旅行灵感'){const s=await api.createSession(title);this.sessions.unshift(s);await this.selectSession(s.session_id);return s},
    /** 删除会话并清理失效的本地选中状态。 */
    async removeSession(id:string){await api.deleteSession(id);this.sessions=this.sessions.filter(x=>x.session_id!==id);if(this.activeSessionId===id){this.activeSessionId=this.sessions[0]?.session_id||'';this.messages=[];this.trips=[]}},
    /** 重新加载当前会话的消息和旅行数据。 */
    async refreshCurrent(){if(this.activeSessionId)await this.selectSession(this.activeSessionId)},
    /** 校验并切换本地用户身份，然后清空会话选择。 */
    switchUser(id:string){const normalized=id.trim().replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,64);if(normalized.length<3)throw new Error('本地身份至少需要 3 个字符');localStorage.setItem('travelmind_user_id',normalized);localStorage.removeItem('travelmind_session_id');window.location.assign('/')},
    /** 短暂显示全局操作提示，并在延时后自动关闭。 */
    showNotice(message:string){this.notice=message;window.setTimeout(()=>{if(this.notice===message)this.notice=''},2600)},
  }
})
