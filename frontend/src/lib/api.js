import axios from "axios";

// Get backend URL — must be set in Vercel environment variables
const getBackendURL = () => {
  const envURL = import.meta.env.VITE_API_URL;

  // Use env var if properly set
  if (envURL &&
      envURL !== "undefined" &&
      envURL !== "" &&
      envURL !== "null") {
    return envURL.replace(/\/$/, "");
  }

  // Local development fallback
  if (typeof window !== "undefined" &&
      (window.location.hostname === "localhost" ||
       window.location.hostname === "127.0.0.1")) {
    return "http://localhost:8000";
  }

  // Production fallback — should never reach here if VITE_API_URL is set
  console.error("❌ VITE_API_URL not set in environment variables");
  return "http://localhost:8000";
};

export const BACKEND_URL = getBackendURL();
console.log("🔗 Backend:", BACKEND_URL);

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 45000,
  headers: {
    "Content-Type": "application/json",
    "Accept":       "application/json",
  },
});

// Add request logging in development
api.interceptors.request.use((config) => {
  if (import.meta.env.DEV) {
    console.log(`→ ${config.method?.toUpperCase()} ${config.url}`, config.params || "");
  }
  return config;
});

// Handle all error types
api.interceptors.response.use(
  (response) => {
    if (import.meta.env.DEV) {
      console.log(`✅ ${response.config.url} — ${response.status}`);
    }
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const url    = error.config?.url || "";

    if (error.code === "ERR_CANCELED" || error.name === "AbortError") {
      error.userMessage = "Request cancelled.";
      return Promise.reject(error);
    }

    if (!error.response) {
      // Network error — backend unreachable
      console.error(`❌ Network error: ${url} — Cannot reach ${BACKEND_URL}`);
      error.userMessage = (
        BACKEND_URL.includes("localhost")
          ? "Backend not running. Run: cd backend && uvicorn main:app --reload --port 8000"
          : `Cannot reach backend at ${BACKEND_URL}. Check Render dashboard.`
      );
    } else if (status === 502) {
      error.userMessage = "Backend crashed (502). Check Render logs at dashboard.render.com";
    } else if (status === 503) {
      error.userMessage = error.response.data?.detail || "Backend starting up. Wait 30s and retry.";
    } else if (status === 422) {
      const detail = error.response.data?.detail;
      error.userMessage = Array.isArray(detail)
        ? detail.map(d => d.msg).join(", ")
        : detail || "Invalid request.";
    } else if (status === 404) {
      error.userMessage = `Endpoint not found: ${url}. Backend may need redeployment.`;
    } else if (status === 500) {
      error.userMessage = error.response.data?.detail || "Server error. Check Render logs.";
    } else {
      error.userMessage = error.response.data?.detail || error.message || "Request failed.";
    }

    console.error(`❌ API Error ${status || "Network"}: ${url} — ${error.userMessage}`);
    return Promise.reject(error);
  }
);

// ── Additional Helper Functions to keep existing methods ───────────────────
export const getOrCreateToken = async () => {
  const existing = localStorage.getItem('careermind_token');
  const userId = localStorage.getItem('careermind_user_id');
  if (existing && userId) return { token: existing, userId };

  // Use raw endpoint request
  const { data } = await api.post('/api/auth/token', {});
  localStorage.setItem('careermind_token', data.access_token);
  localStorage.setItem('careermind_user_id', data.user_id);
  return { token: data.access_token, userId: data.user_id };
};

export const getUserId = () => localStorage.getItem('careermind_user_id') || 'guest';

export const uploadResume = async (file, userId = '') => {
  const formData = new FormData();
  formData.append('file', file);
  if (userId) formData.append('user_id', userId);
  const { data } = await api.post('/api/upload-resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export const analyzeResume = async ({ filePath, userId, jobQuery = 'Software Engineer', jobLocation = 'United States' }) => {
  const { data } = await api.post('/api/analyze', {
    file_path: filePath,
    user_id: userId,
    job_query: jobQuery,
    job_location: jobLocation,
  });
  return data;
};

export const fetchJobs = async ({ query, location, userId }) => {
  const { data } = await api.get('/api/jobs', {
    params: {
      q: query,
      location,
      user_id: userId,
    },
  });
  return data;
};

export const rewriteResume = async ({ resumeText, resumePath, job, userId }) => {
  const { data } = await api.post('/api/rewrite', {
    resume_text: resumeText,
    resume_path: resumePath,
    job,
    user_id: userId,
  });
  return data;
};

export const getInterviewQuestion = async ({ jobTitle, roundNumber, history = [] }) => {
  const { data } = await api.post('/api/interview/question', {
    job_title: jobTitle,
    round_number: roundNumber,
    history,
  });
  return data;
};

export const scoreInterviewAnswer = async ({ audioBlob, question, jobTitle, userId, answerText = '' }) => {
  const formData = new FormData();
  if (audioBlob) formData.append('audio', audioBlob, 'answer.webm');
  formData.append('question', question);
  formData.append('job_title', jobTitle);
  formData.append('user_id', userId || '');
  if (answerText) formData.append('answer_text', answerText);

  const { data } = await api.post('/api/interview/score', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export const getSession = async (userId) => {
  const { data } = await api.get(`/api/session/${userId}`);
  return data;
};

export const checkHealth = async () => {
  const { data } = await api.get('/api/health');
  return data;
};

export default api;
