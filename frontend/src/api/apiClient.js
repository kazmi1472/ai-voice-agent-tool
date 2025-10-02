import axios from 'axios'

// Backend base URL comes from env; fallback left simple for local dev
const baseURL = (import.meta?.env?.VITE_BACKEND_URL) || 'http://localhost:8000'

console.log('Frontend API Client - baseURL:', baseURL)
console.log('Frontend API Client - VITE_BACKEND_URL:', import.meta.env.VITE_BACKEND_URL)

// Guard: never expose keys
if (typeof process !== 'undefined') {
  if (process.env.RETELL_API_KEY || process.env.OPENAI_API_KEY) {
    console.warn('Security guard: Keys must not be present in frontend env')
  }
}

export const api = axios.create({ baseURL: `${baseURL}/api` })

// Add request interceptor for debugging
api.interceptors.request.use(
  (config) => {
    console.log('API Request:', config.method?.toUpperCase(), config.url, config.data)
    return config
  },
  (error) => {
    console.error('API Request Error:', error)
    return Promise.reject(error)
  }
)

// Add response interceptor for debugging
api.interceptors.response.use(
  (response) => {
    console.log('API Response:', response.status, response.config.url, response.data)
    return response
  },
  (error) => {
    console.error('API Response Error:', error.response?.status, error.config?.url, error.message)
    return Promise.reject(error)
  }
)

export const AgentConfigs = {
  list: () => api.get('/agent-configs').then(r => r.data),
  create: (data) => api.post('/agent-configs', data).then(r => r.data),
  update: (id, data) => api.put(`/agent-configs/${id}`, data).then(r => r.data),
  delete: (id) => api.delete(`/agent-configs/${id}`).then(r => r.data)
}

export const Calls = {
  start: (payload, local=false) => api.post(`/calls/start${local ? '?mode=local' : ''}`, payload).then(r => r.data),
  list: (params) => api.get('/calls', { params }).then(r => r.data),
  get: (id) => api.get(`/calls/${id}`).then(r => r.data),
  process: (id) => api.post(`/calls/${id}/process`).then(r => r.data)
}
