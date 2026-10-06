import type { MessageItem, SessionItem, TripItem, TripVersion, MemoryItem, RagSource, RagDocument, ToolInvokeResult } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'
/** 返回当前浏览器保存的本地用户标识。 */
const userId = () => localStorage.getItem('travelmind_user_id') || 'demo_traveler'

/** 发送带用户上下文的 API 请求，并将非成功响应转换为异常。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', 'X-User-ID': userId(), ...init.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.error?.message || body?.detail || `请求失败 (${response.status})`)
  }
  return response.json()
}

export const api = {
  health: () => request<{status:string;database:boolean}>('/health'),
  sessions: () => request<SessionItem[]>('/sessions'),
  createSession: (title?:string) => request<SessionItem>('/sessions', { method:'POST', body:JSON.stringify({title}) }),
  deleteSession: (id:string) => request(`/sessions/${id}`, {method:'DELETE'}),
  messages: (id:string) => request<MessageItem[]>(`/sessions/${id}/messages`),
  trips: (sessionId:string) => request<TripItem[]>(`/trips?session_id=${encodeURIComponent(sessionId)}`),
  tripVersions: (tripId:string, sessionId:string) => request<TripVersion[]>(`/trips/${tripId}/versions?session_id=${encodeURIComponent(sessionId)}`),
  editActivity: (tripId:string, sessionId:string, payload:Record<string,unknown>) => request(`/trips/${tripId}/activities/edit?session_id=${encodeURIComponent(sessionId)}`, {method:'POST',body:JSON.stringify(payload)}),
  feedback: (tripId:string, sessionId:string, payload:Record<string,unknown>) => request(`/trips/${tripId}/feedback?session_id=${encodeURIComponent(sessionId)}`, {method:'POST',body:JSON.stringify(payload)}),
  memories: () => request<MemoryItem[]>('/memory'),
  memorySettings: () => request<{personalization_enabled:boolean;long_term_memory_enabled:boolean}>('/memory/settings'),
  updateMemorySettings: (payload:Record<string,boolean>) => request<{personalization_enabled:boolean;long_term_memory_enabled:boolean}>('/memory/settings',{method:'POST',body:JSON.stringify(payload)}),
  updateMemory: (id:string, statement:string) => request<MemoryItem>(`/memory/${id}`,{method:'PATCH',body:JSON.stringify({statement})}),
  deleteMemory: (id:string) => request(`/memory/${id}`,{method:'DELETE'}),
  sources: () => request<RagSource[]>('/rag/sources'),
  documents: () => request<RagDocument[]>('/rag/documents'),
  createSource: (payload:Record<string,unknown>) => request<RagSource>('/rag/sources',{method:'POST',body:JSON.stringify(payload)}),
  ingestDocument: (sourceId:string,payload:Record<string,unknown>) => request(`/rag/sources/${sourceId}/documents`,{method:'POST',body:JSON.stringify(payload)}),
  deleteDocument: (id:string) => request(`/rag/documents/${id}`,{method:'DELETE'}),
  toolHealth: () => request<Record<string,Record<string,unknown>>>('/tools/health'),
  invokeTool: (name:string, arguments_:Record<string,unknown>, sessionId?:string, tripId?:string) => request<ToolInvokeResult>(`/tools/${name}/invoke`,{method:'POST',body:JSON.stringify({arguments:arguments_,session_id:sessionId,trip_id:tripId})}),
  enrichTripMap: (tripId:string, sessionId:string) => request<any>(`/trips/${tripId}/map/enrich?session_id=${encodeURIComponent(sessionId)}`,{method:'POST'}),
}

/** 消费会话 SSE 接口，并把解析后的事件逐个交给页面回调。 */
export async function streamMessage(sessionId:string,message:string,onEvent:(event:string,data:any)=>void) {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/messages/stream`, { method:'POST', headers:{'Content-Type':'application/json','X-User-ID':userId()}, body:JSON.stringify({message}) })
  if (!response.ok || !response.body) throw new Error(`无法连接对话服务 (${response.status})`)
  const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer=''
  while (true) {
    const {value,done}=await reader.read(); buffer+=decoder.decode(value||new Uint8Array(),{stream:!done})
    const blocks=buffer.split('\n\n'); buffer=blocks.pop()||''
    for (const block of blocks) { let event='message',data='{}'; for(const line of block.split('\n')) { if(line.startsWith('event:')) event=line.slice(6).trim(); if(line.startsWith('data:')) data=line.slice(5).trim() } onEvent(event,JSON.parse(data)) }
    if(done) break
  }
}
