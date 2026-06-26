import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  updateProfile,
  sendPasswordResetEmail,
} from "firebase/auth";

const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
const isFirebaseConfigured = apiKey && 
  apiKey !== "" && 
  !apiKey.includes("placeholder") && 
  !apiKey.includes("AIza...");

let authInstance = null;
let useMockAuth = false;

if (isFirebaseConfigured) {
  try {
    const firebaseConfig = {
      apiKey:            apiKey,
      authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
      storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
      appId:             import.meta.env.VITE_FIREBASE_APP_ID,
    };
    const app = initializeApp(firebaseConfig);
    authInstance = getAuth(app);
    console.log("Firebase Auth initialized successfully.");
  } catch (err) {
    console.error("Firebase initialization failed, falling back to Mock Auth:", err);
    useMockAuth = true;
  }
} else {
  console.warn("Firebase credentials not configured in frontend/.env. falling back to Mock Auth (Demo Mode).");
  useMockAuth = true;
}

// ── REAL FIREBASE METHODS ─────────────────────────────────────────────
const realSignInWithGoogle = async () => {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  const result = await signInWithPopup(authInstance, provider);
  return result.user;
};

const realSignInWithEmail = async (email, password) => {
  const result = await signInWithEmailAndPassword(authInstance, email, password);
  return result.user;
};

const realRegisterWithEmail = async (name, email, password) => {
  const result = await createUserWithEmailAndPassword(authInstance, email, password);
  await updateProfile(result.user, { displayName: name });
  return result.user;
};

const realResetPassword = async (email) => {
  await sendPasswordResetEmail(authInstance, email);
};

const realLogOut = async () => {
  await signOut(authInstance);
};

const realOnAuthChange = (callback) => {
  return onAuthStateChanged(authInstance, callback);
};

// ── MOCK AUTHENTICATION SYSTEM (DEMO MODE FALLBACK) ──────────────────
// Ensures the app never crashes with a blank screen if Firebase is not yet set up.
const mockUsersDbKey = "careermind_mock_users";
const mockSessionKey = "careermind_mock_session";

const getMockUsers = () => {
  try {
    return JSON.parse(localStorage.getItem(mockUsersDbKey) || "[]");
  } catch {
    return [];
  }
};

const saveMockUsers = (users) => {
  localStorage.setItem(mockUsersDbKey, JSON.stringify(users));
};

const getMockSession = () => {
  try {
    return JSON.parse(localStorage.getItem(mockSessionKey) || "null");
  } catch {
    return null;
  }
};

const setMockSession = (user) => {
  if (user) {
    localStorage.setItem(mockSessionKey, JSON.stringify(user));
  } else {
    localStorage.removeItem(mockSessionKey);
  }
  // Trigger mock auth state listeners
  mockAuthListeners.forEach(listener => listener(user));
};

const mockAuthListeners = new Set();

const mockSignInWithGoogle = async () => {
  await new Promise(r => setTimeout(r, 800)); // Simulate network latency
  const mockGoogleUser = {
    uid: "google-mock-12345",
    displayName: "Vedant Bhatt (Demo)",
    email: "vedant@example.com",
    photoURL: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&h=150&q=80",
    providerData: [{ providerId: "google.com" }]
  };
  setMockSession(mockGoogleUser);
  return mockGoogleUser;
};

const mockSignInWithEmail = async (email, password) => {
  await new Promise(r => setTimeout(r, 600));
  const users = getMockUsers();
  const user = users.find(u => u.email === email.toLowerCase());
  
  if (!user) {
    const err = new Error("No account found with this email.");
    err.code = "auth/user-not-found";
    throw err;
  }
  
  if (user.password !== password) {
    const err = new Error("Incorrect password.");
    err.code = "auth/wrong-password";
    throw err;
  }
  
  const sessionUser = {
    uid: user.uid,
    displayName: user.displayName,
    email: user.email,
    photoURL: null,
    providerData: [{ providerId: "password" }]
  };
  setMockSession(sessionUser);
  return sessionUser;
};

const mockRegisterWithEmail = async (name, email, password) => {
  await new Promise(r => setTimeout(r, 800));
  const users = getMockUsers();
  
  if (users.some(u => u.email === email.toLowerCase())) {
    const err = new Error("Email already in use.");
    err.code = "auth/email-already-in-use";
    throw err;
  }
  
  const newUser = {
    uid: "user-" + Math.random().toString(36).substr(2, 9),
    displayName: name,
    email: email.toLowerCase(),
    password: password
  };
  
  users.push(newUser);
  saveMockUsers(users);
  
  const sessionUser = {
    uid: newUser.uid,
    displayName: newUser.displayName,
    email: newUser.email,
    photoURL: null,
    providerData: [{ providerId: "password" }]
  };
  setMockSession(sessionUser);
  return sessionUser;
};

const mockResetPassword = async (email) => {
  await new Promise(r => setTimeout(r, 500));
  const users = getMockUsers();
  const exists = users.some(u => u.email === email.toLowerCase()) || email.toLowerCase().includes("@");
  if (!exists) {
    const err = new Error("Email not found.");
    err.code = "auth/user-not-found";
    throw err;
  }
  return true;
};

const mockLogOut = async () => {
  setMockSession(null);
};

const mockOnAuthChange = (callback) => {
  mockAuthListeners.add(callback);
  // Trigger initial state callback
  const currentSession = getMockSession();
  callback(currentSession);
  
  return () => {
    mockAuthListeners.delete(callback);
  };
};

// ── EXPORTS (AUTO-SWITCHING) ──────────────────────────────────────────
export const signInWithGoogle = useMockAuth ? mockSignInWithGoogle : realSignInWithGoogle;
export const signInWithEmail = useMockAuth ? mockSignInWithEmail : realSignInWithEmail;
export const registerWithEmail = useMockAuth ? mockRegisterWithEmail : realRegisterWithEmail;
export const resetPassword = useMockAuth ? mockResetPassword : realResetPassword;
export const logOut = useMockAuth ? mockLogOut : realLogOut;
export const onAuthChange = useMockAuth ? mockOnAuthChange : realOnAuthChange;
