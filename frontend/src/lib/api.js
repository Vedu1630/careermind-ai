import axios from "axios";

const getBackendURL = () => {
  const env = import.meta.env.VITE_API_URL;
  if (env && env.trim() && env !== "undefined" && env !== "null") {
    return env.replace(/\/$/, "");
  }
  return "http://localhost:8000";
};

export const BACKEND_URL = getBackendURL();
console.log("🔗 Backend:", BACKEND_URL);

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 120000,
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json",
  },
});

api.interceptors.request.use(config => {
  console.log(`→ ${config.method?.toUpperCase()} ${config.url}`);
  return config;
});

api.interceptors.response.use(
  res => res,
  error => {
    const status = error.response?.status;
    if (!error.response) {
      error.userMessage = BACKEND_URL.includes("localhost")
        ? "Backend not running. Start it: cd backend && uvicorn main:app --reload --port 8000"
        : "Backend is sleeping. Wait 60 seconds and click retry.";
    } else if (status === 502) {
      error.userMessage = "Server error (502). Wait 30 seconds and retry.";
    } else if (status === 404) {
      error.userMessage = error.response?.data?.detail || `Not found: ${error.config?.url}`;
    } else if (status === 422) {
      const d = error.response.data?.detail;
      error.userMessage = Array.isArray(d) ? d.map(x => x.msg).join(", ") : d || "Invalid request.";
    } else {
      error.userMessage = error.response?.data?.detail || error.message || "Request failed.";
    }
    return Promise.reject(error);
  }
);

/**
 * Poll backend health until it responds or timeout.
 * Calls onProgress(secondsWaited, maxSeconds) every second.
 * Returns true if backend woke up, false if timed out.
 */
export const waitForBackend = async (
  onProgress,
  maxWaitSeconds = 120
) => {
  const startTime = Date.now();
  let attempt = 0;

  while (Date.now() - startTime < maxWaitSeconds * 1000) {
    attempt++;
    const secondsWaited = Math.floor((Date.now() - startTime) / 1000);
    onProgress?.(secondsWaited, maxWaitSeconds);

    try {
      const res = await axios.get(`${BACKEND_URL}/health`, {
        timeout: 10000,
      });
      if (res.data?.status === "online" || res.status === 200) {
        console.log(`✅ Backend awake after ${secondsWaited}s`);
        return true;
      }
    } catch (err) {
      // Still sleeping — keep waiting
      console.log(`⏳ Backend not ready yet (${secondsWaited}s elapsed)...`);
    }

    // Wait 3 seconds between attempts
    await new Promise(r => setTimeout(r, 3000));
  }

  console.error(`❌ Backend did not wake up within ${maxWaitSeconds}s`);
  return false;
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
