// At the very top of src/main.jsx
const backendURL = import.meta.env.VITE_API_URL;
if (!backendURL || backendURL === "undefined") {
  console.error(
    "❌ VITE_API_URL is not set!\n" +
    "Go to Vercel → Settings → Environment Variables → Add:\n" +
    "VITE_API_URL = https://careermind-backend.onrender.com\n" +
    "Then redeploy the frontend."
  );
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
