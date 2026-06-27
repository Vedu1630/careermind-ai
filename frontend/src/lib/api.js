import axios from 'axios'

// Request deduplication — cancel duplicate in-flight requests
const pendingRequests = new Map()

// Determine backend URL
const getBaseURL = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (window.location.hostname !== "localhost" &&
      window.location.hostname !== "127.0.0.1") {
    return "/api";
  }
  return "http://localhost:8000";
};

// ── Axios instance ─────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 180000, // 180s (3m) for AI processing
  headers: { 'Content-Type': 'application/json' },
})

// Log every request for debugging, inject auth token, and handle request deduplication
api.interceptors.request.use((config) => {
  console.log(`🌐 API ${config.method?.toUpperCase()} ${config.baseURL || ''}${config.url}`);
  
  const token = localStorage.getItem('careermind_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }

  // Deduplication logic
  const key = `${config.method}:${config.url}:${JSON.stringify(config.params || {})}`
  if (pendingRequests.has(key)) {
    pendingRequests.get(key).abort()
  }

  const controller = new AbortController()
  config.signal = controller.signal
  pendingRequests.set(key, controller)

  return config
})

// Response interceptor to handle errors clearly, handle 401 Unauthorized, and clean up pending requests
api.interceptors.response.use(
  (response) => {
    const key = `${response.config.method}:${response.config.url}:${JSON.stringify(response.config.params || {})}`
    pendingRequests.delete(key)
    return response
  },
  async (error) => {
    if (error.config) {
      const key = `${error.config.method}:${error.config.url}:${JSON.stringify(error.config.params || {})}`
      pendingRequests.delete(key)
    }

    if (axios.isCancel(error)) {
      console.log("Duplicate request cancelled")
      return Promise.reject(error)
    }

    // Handle errors clearly
    if (error.code === "ERR_NETWORK" || error.message === "Network Error") {
      console.error("❌ Cannot reach backend. Is it running?");
      error.userMessage = "Cannot connect to server. Make sure the backend is running.";
    } else if (error.response?.status === 502) {
      console.error("❌ 502 Bad Gateway — backend crashed or not running");
      error.userMessage = "Server error (502). The backend may have crashed.";
    } else if (error.response?.status === 503) {
      error.userMessage = error.response.data?.detail || "Service temporarily unavailable.";
    }

    const originalRequest = error.config
    
    // Guard against undefined config/response and prevent recursive authentication loops on /auth/token
    const isAuthPath = originalRequest && originalRequest.url && originalRequest.url.includes('/auth/token')
    
    if (
      error.response && 
      error.response.status === 401 && 
      originalRequest && 
      !originalRequest._retry && 
      !isAuthPath
    ) {
      originalRequest._retry = true
      
      // Clear the invalid token from localStorage
      localStorage.removeItem('careermind_token')
      localStorage.removeItem('careermind_user_id')
      
      try {
        // Fetch a fresh token
        const { token } = await getOrCreateToken()
        
        // Update the header of the original request and retry it
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${token}`
        return api(originalRequest)
      } catch (tokenError) {
        console.error("Failed to refresh auth token:", tokenError)
        return Promise.reject(error) // Always reject to prevent returning undefined and crashing React
      }
    }
    
    return Promise.reject(error) // Always reject to prevent returning undefined and crashing React
  }
)

// ── Auth ────────────────────────────────────────────────────────────────────
export const getOrCreateToken = async () => {
  const existing = localStorage.getItem('careermind_token')
  const userId = localStorage.getItem('careermind_user_id')
  if (existing && userId) return { token: existing, userId }

  const { data } = await api.post('/auth/token', {})
  localStorage.setItem('careermind_token', data.access_token)
  localStorage.setItem('careermind_user_id', data.user_id)
  return { token: data.access_token, userId: data.user_id }
}

export const getUserId = () => localStorage.getItem('careermind_user_id') || 'guest'

// ── Resume ──────────────────────────────────────────────────────────────────
export const uploadResume = async (file, userId = '') => {
  const formData = new FormData()
  formData.append('file', file)
  if (userId) formData.append('user_id', userId)
  const { data } = await api.post('/upload-resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const analyzeResume = async ({ filePath, userId, jobQuery = 'Software Engineer', jobLocation = 'United States' }) => {
  const { data } = await api.post('/analyze', {
    file_path: filePath,
    user_id: userId,
    job_query: jobQuery,
    job_location: jobLocation,
  })
  return data
}

// ── Jobs ────────────────────────────────────────────────────────────────────
export const fetchJobs = async ({ query, location, userId }) => {
  const { data } = await api.get('/jobs', {
    params: {
      q: query,
      location,
      user_id: userId,
    },
  })
  return data
}

// ── Resume Rewriter ─────────────────────────────────────────────────────────
export const rewriteResume = async ({ resumeText, resumePath, job, userId }) => {
  const { data } = await api.post('/rewrite', {
    resume_text: resumeText,
    resume_path: resumePath,
    job,
    user_id: userId,
  })
  return data
}

// ── Interview ───────────────────────────────────────────────────────────────
export const getInterviewQuestion = async ({ jobTitle, roundNumber, history = [] }) => {
  const { data } = await api.post('/interview/question', {
    job_title: jobTitle,
    round_number: roundNumber,
    history,
  })
  return data
}

export const scoreInterviewAnswer = async ({ audioBlob, question, jobTitle, userId, answerText = '' }) => {
  const formData = new FormData()
  if (audioBlob) formData.append('audio', audioBlob, 'answer.webm')
  formData.append('question', question)
  formData.append('job_title', jobTitle)
  formData.append('user_id', userId || '')
  if (answerText) formData.append('answer_text', answerText)

  const { data } = await api.post('/interview/score', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Session ─────────────────────────────────────────────────────────────────
export const getSession = async (userId) => {
  const { data } = await api.get(`/session/${userId}`)
  return data
}

// ── Health ──────────────────────────────────────────────────────────────────
export const checkHealth = async () => {
  const { data } = await api.get('/health')
  return data
}

export default api
