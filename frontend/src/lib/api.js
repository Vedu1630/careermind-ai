import axios from "axios";

const getBackendURL = () => {
  // Check env var set in Vercel dashboard
  const env = import.meta.env.VITE_API_URL;
  if (env && env !== "undefined" && env !== "" && env !== "null") {
    return env.replace(/\/$/, "");
  }
  // Local fallback
  return "http://localhost:8000";
};

export const BACKEND_URL = getBackendURL();
console.log("🔗 Backend:", BACKEND_URL);

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 90000,  // 90 seconds — handles Render cold start
  headers: {
    "Content-Type": "application/json",
    "Accept":       "application/json",
  },
});

api.interceptors.request.use(config => {
  console.log(`→ ${config.method?.toUpperCase()} ${config.baseURL}${config.url}`);
  return config;
});

api.interceptors.response.use(
  res => res,
  error => {
    const status = error.response?.status;
    if (!error.response) {
      error.userMessage = `Cannot reach backend at ${BACKEND_URL}`;
    } else if (status === 404) {
      error.userMessage = `Endpoint not found: ${error.config?.url} — backend needs redeployment`;
    } else if (status === 502) {
      error.userMessage = "Backend crashed (502) — check Render logs";
    } else if (status === 503) {
      error.userMessage = "Backend waking up — wait 30s and retry";
    } else {
      error.userMessage = error.response?.data?.detail || error.message || "Request failed";
    }
    console.error(`❌ ${status || "Network"}: ${error.config?.url} — ${error.userMessage}`);
    return Promise.reject(error);
  }
);

// Wake up backend on app load to reduce cold start for first real request
export const wakeUpBackend = async () => {
  try {
    console.log("🔄 Waking up backend...");
    await axios.get(`${BACKEND_URL}/health`, { timeout: 90000 });
    console.log("✅ Backend is awake");
    return true;
  } catch (e) {
    console.warn("⚠️ Backend wake-up:", e.message);
    return false;
  }
};

// ── Additional Helper Functions to keep existing methods ───────────────────
export const getOrCreateToken = async () => {
  const existing = localStorage.getItem('careermind_token');
  const userId = localStorage.getItem('careermind_user_id');
  if (existing && userId) return { token: existing, userId };

  try {
    const { data } = await api.post('/api/auth/token', {});
    localStorage.setItem('careermind_token', data.access_token);
    localStorage.setItem('careermind_user_id', data.user_id);
    return { token: data.access_token, userId: data.user_id };
  } catch (e) {
    // Auth endpoint may not exist — generate a local guest ID
    const guestId = 'guest_' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem('careermind_user_id', guestId);
    localStorage.setItem('careermind_token', 'local');
    return { token: 'local', userId: guestId };
  }
};

export const getUserId = () => localStorage.getItem('careermind_user_id') || 'guest';

export const uploadResume = async (file, userId = '') => {
  const formData = new FormData();
  formData.append('file', file);
  if (userId) formData.append('user_id', userId);
  const { data } = await api.post('/api/upload-resume', formData);
  return data;
};

export const analyzeResume = async ({ filePath, userId, jobQuery = '', jobLocation = 'United States' }) => {
  const { data } = await api.post('/api/analyze', {
    resume_path: filePath,
    user_id: userId,
    job_description: jobQuery,
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

  const { data } = await api.post('/api/interview/score', formData);
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
