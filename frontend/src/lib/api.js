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

// Standard API instance
const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 90000,  // 90 seconds — handles Render cold start
  headers: {
    "Content-Type": "application/json",
    "Accept":       "application/json",
  },
});

api.interceptors.request.use((config) => {
  if (import.meta.env.DEV) {
    console.log(`→ ${config.method?.toUpperCase()} ${config.url}`);
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error.response?.status;
    if (!error.response) {
      error.userMessage =
        BACKEND_URL.includes("localhost")
          ? "Backend not running. Run: cd backend && uvicorn main:app --reload --port 8000"
          : "Backend is waking up from sleep. Please wait 30-60 seconds and try again.";
    } else if (status === 502) {
      error.userMessage = "Server error (502). Backend may be restarting — wait 30s and retry.";
    } else if (status === 503) {
      error.userMessage = "Backend is starting up. Wait 30 seconds and retry.";
    } else if (status === 404) {
      error.userMessage = `Endpoint not found: ${error.config?.url}`;
    } else if (status === 422) {
      const d = error.response.data?.detail;
      error.userMessage = Array.isArray(d) ? d.map(x=>x.msg).join(", ") : d || "Invalid request.";
    } else {
      error.userMessage = error.response?.data?.detail || error.message || "Request failed.";
    }
    return Promise.reject(error);
  }
);

/**
 * Wake up the backend — call this before any important action.
 * Shows real-time status. Returns true if backend is ready.
 */
export const wakeUpBackend = async (onStatus) => {
  const isProduction = !BACKEND_URL.includes("localhost");

  try {
    onStatus?.("checking");
    const res = await axios.get(`${BACKEND_URL}/health`, { timeout: 90000 });
    if (res.data?.status === "online") {
      onStatus?.("ready");
      return true;
    }
  } catch (err) {
    if (isProduction) {
      // Production: backend is sleeping — wait and retry
      onStatus?.("waking");
      // Give Render time to wake up
      await new Promise(r => setTimeout(r, 15000));
      // Retry
      try {
        const res2 = await axios.get(`${BACKEND_URL}/health`, { timeout: 90000 });
        if (res2.data) {
          onStatus?.("ready");
          return true;
        }
      } catch (err2) {
        onStatus?.("failed");
        return false;
      }
    } else {
      onStatus?.("failed");
      return false;
    }
  }
  return false;
};

export default api;
