import axios from 'axios'

// Request deduplication — cancel duplicate in-flight requests
const pendingRequests = new Map()

const getBaseURL = () => {
  // 1. Explicit env var — highest priority
  const envURL = import.meta.env.VITE_API_URL;
  if (envURL && envURL !== "undefined" && envURL !== "") {
    let url = envURL.replace(/\/$/, ""); // strip trailing slash
    if (!url.endsWith("/api")) {
      url += "/api";
    }
    return url;
  }

  // 2. If running on Vercel/Render production — use deployed backend
  const host = window.location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1") {
    console.warn("⚠️ VITE_API_URL not set. Set it to your backend URL in Vercel environment variables.");
    return "http://localhost:8000/api"; // Will fail in prod — forces user to set env var
  }

  // 3. Local development default
  return "http://localhost:8000/api";
};

const BASE_URL = getBaseURL();
console.log("🔗 API connecting to:", BASE_URL);

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 180000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  console.log(`→ ${config.method?.toUpperCase()} ${config.url}`);
  
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
});

api.interceptors.response.use(
  (res) => {
    const key = `${res.config.method}:${res.config.url}:${JSON.stringify(res.config.params || {})}`
    pendingRequests.delete(key)
    return res;
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

    const status = error.response?.status;
    const url    = error.config?.url;

    if (!error.response) {
      console.error(`❌ Network error on ${url} — backend not reachable at ${BASE_URL}`);
      error.userMessage = `Cannot reach backend at ${BASE_URL}. Is it running?`;
    } else if (status === 502) {
      console.error(`❌ 502 on ${url} — backend crashed or restarting`);
      error.userMessage = "Server error (502). Backend may be restarting.";
    } else if (status === 503) {
      error.userMessage = error.response.data?.detail || "Service unavailable.";
    } else if (status === 404) {
      error.userMessage = `Endpoint not found: ${url}`;
    } else if (status === 422) {
      error.userMessage = error.response.data?.detail || "Invalid request data.";
    }

    const originalRequest = error.config
    const isAuthPath = originalRequest && originalRequest.url && originalRequest.url.includes('/auth/token')

    if (
      error.response && 
      error.response.status === 401 && 
      originalRequest && 
      !originalRequest._retry && 
      !isAuthPath
    ) {
      originalRequest._retry = true
      localStorage.removeItem('careermind_token')
      localStorage.removeItem('careermind_user_id')
      try {
        const { token } = await getOrCreateToken()
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${token}`
        return api(originalRequest)
      } catch (tokenError) {
        console.error("Failed to refresh auth token:", tokenError)
        return Promise.reject(error)
      }
    }

    return Promise.reject(error);
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
