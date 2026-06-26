import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Eye, EyeOff, Mail, Lock, User, AlertCircle, Loader2, ArrowLeft } from "lucide-react";
import {
  signInWithGoogle,
  signInWithEmail,
  registerWithEmail,
  resetPassword,
} from "../lib/firebase";
import useAuthStore from "../store/useAuthStore";

const GOOGLE_ICON = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908C16.658 14.013 17.64 11.705 17.64 9.2z" fill="#4285F4"/>
    <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
    <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
    <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
  </svg>
);

const LOGO = (
  <div className="flex items-center gap-2 mb-8">
    <div className="w-8 h-8 bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8]
                    rounded-lg flex items-center justify-center shadow-md">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 1.5L13.5 4.5V11.5L8 14.5L2.5 11.5V4.5L8 1.5Z"
          stroke="white" strokeWidth="1.2" fill="none"/>
        <circle cx="8" cy="8" r="2.2" fill="white"/>
      </svg>
    </div>
    <span className="text-[15px] font-extrabold text-[#111] tracking-tight">
      CareerMind AI
    </span>
  </div>
);

function ErrorBanner({ message, onClose }) {
  if (!message) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex items-start gap-2 p-3 bg-[#FEE2E2] border border-[#FECACA]
                 rounded-xl mb-4 animate-shake"
    >
      <AlertCircle className="w-4 h-4 text-[#DC2626] shrink-0 mt-0.5" />
      <p className="text-[12px] text-[#DC2626] flex-1 font-medium">{message}</p>
      <button onClick={onClose} className="text-[#DC2626] hover:opacity-70 text-lg leading-none cursor-pointer">×</button>
    </motion.div>
  );
}

function SuccessBanner({ message }) {
  if (!message) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 p-3 bg-[#DCFCE7] border border-[#BBF7D0]
                 rounded-xl mb-4"
    >
      <div className="w-4 h-4 text-[#16A34A] font-bold">✓</div>
      <p className="text-[12px] text-[#16A34A] font-medium">{message}</p>
    </motion.div>
  );
}

export default function Auth() {
  const navigate  = useNavigate();
  const { error, setError, clearError } = useAuthStore();

  const [tab,       setTab]       = useState("signin");
  const [showPass,  setShowPass]  = useState(false);
  const [showPass2, setShowPass2] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [gLoading,  setGLoading]  = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [resetEmail, setResetEmail] = useState("");
  const [resetSent, setResetSent] = useState(false);
  const [success,   setSuccess]   = useState("");

  const [form, setForm] = useState({
    name: "", email: "", password: "", confirm: ""
  });

  const upd = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    clearError();
    setSuccess("");
  };

  const switchTab = (t) => {
    setTab(t);
    clearError();
    setSuccess("");
    setShowReset(false);
    setForm({ name: "", email: "", password: "", confirm: "" });
  };

  const errMsg = (code) => ({
    "auth/user-not-found":        "No account found with this email.",
    "auth/wrong-password":        "Incorrect password. Try again.",
    "auth/invalid-credential":    "Incorrect email or password.",
    "auth/email-already-in-use":  "This email is already registered.",
    "auth/weak-password":         "Password must be at least 6 characters.",
    "auth/invalid-email":         "Please enter a valid email address.",
    "auth/too-many-requests":     "Too many attempts. Please wait and try again.",
    "auth/network-request-failed":"Network error. Check your connection.",
    "auth/popup-blocked":         "Popup blocked. Please allow popups for this site.",
    "auth/popup-closed-by-user":  null, // silent — user closed popup intentionally
  }[code] || "Something went wrong. Please try again.");

  // ── GOOGLE ────────────────────────────────────────────────────────
  const handleGoogle = async () => {
    setGLoading(true);
    clearError();
    try {
      await signInWithGoogle();
      navigate("/dashboard");
    } catch (err) {
      const msg = errMsg(err.code);
      if (msg) setError(msg);
    } finally {
      setGLoading(false);
    }
  };

  // ── SIGN IN ───────────────────────────────────────────────────────
  const handleSignIn = async (e) => {
    e.preventDefault();
    if (!form.email.trim()) { setError("Email is required."); return; }
    if (!form.password)     { setError("Password is required."); return; }
    setLoading(true);
    clearError();
    try {
      await signInWithEmail(form.email.trim(), form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(errMsg(err.code));
    } finally {
      setLoading(false);
    }
  };

  // ── REGISTER ──────────────────────────────────────────────────────
  const handleRegister = async (e) => {
    e.preventDefault();
    if (!form.name.trim())    { setError("Full name is required."); return; }
    if (!form.email.trim())   { setError("Email is required."); return; }
    if (!form.password)       { setError("Password is required."); return; }
    if (form.password.length < 6) { setError("Password must be at least 6 characters."); return; }
    if (form.password !== form.confirm) { setError("Passwords don't match."); return; }
    setLoading(true);
    clearError();
    try {
      await registerWithEmail(form.name.trim(), form.email.trim(), form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(errMsg(err.code));
    } finally {
      setLoading(false);
    }
  };

  // ── RESET PASSWORD ────────────────────────────────────────────────
  const handleReset = async (e) => {
    e.preventDefault();
    if (!resetEmail.trim()) { setError("Enter your email address."); return; }
    setLoading(true);
    clearError();
    try {
      await resetPassword(resetEmail.trim());
      setResetSent(true);
      setSuccess("Reset email sent! Check your inbox.");
    } catch (err) {
      setError(errMsg(err.code));
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full pl-10 pr-4 py-3 border-[1.5px] border-[#E8E4FF] rounded-xl " +
    "text-[13px] text-[#111] bg-[#FAFAFA] outline-none transition-all " +
    "focus:border-[#6B5CE7] focus:bg-white placeholder:text-[#CCC]";

  const labelClass = "text-[11px] font-semibold text-[#555] block mb-1.5";

  return (
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-[#F0EEFF]">

      {/* ── LEFT: Form ── */}
      <div className="bg-white flex items-center justify-center px-8 py-10 md:px-14">
        <div className="w-full max-w-sm">
          {LOGO}

          {/* Tabs */}
          <div className="flex bg-[#F0EEFF] rounded-xl p-1 mb-7">
            {["signin", "register"].map(t => (
              <button
                key={t}
                type="button"
                onClick={() => switchTab(t)}
                className={`flex-1 py-2 rounded-[10px] text-[12px] font-semibold
                            transition-all cursor-pointer ${
                  tab === t
                    ? "bg-white text-[#6B5CE7] shadow-sm"
                    : "text-[#888] hover:text-[#555]"
                }`}
              >
                {t === "signin" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">

            {/* ── FORGOT PASSWORD VIEW ── */}
            {showReset ? (
              <motion.div key="reset"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <button
                  type="button"
                  onClick={() => { setShowReset(false); clearError(); setResetSent(false); setSuccess(""); }}
                  className="flex items-center gap-1.5 text-[12px] text-[#888]
                             hover:text-[#6B5CE7] mb-5 transition-colors cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back to Sign In
                </button>

                <h2 className="text-2xl font-extrabold text-[#111] tracking-tight mb-1">
                  Reset password
                </h2>
                <p className="text-[13px] text-[#888] mb-6">
                  Enter your email and we'll send a reset link.
                </p>

                <AnimatePresence>
                  <ErrorBanner message={error} onClose={clearError} />
                  <SuccessBanner message={success} />
                </AnimatePresence>

                {!resetSent && (
                  <form onSubmit={handleReset} noValidate>
                    <div className="mb-5">
                      <label className={labelClass}>Email address</label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type="email"
                          placeholder="you@example.com"
                          className={inputClass}
                          value={resetEmail}
                          onChange={e => { setResetEmail(e.target.value); clearError(); }}
                        />
                      </div>
                    </div>
                    <button
                      type="submit"
                      disabled={loading}
                      className="w-full py-3 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                                 rounded-xl text-[14px] font-bold text-white
                                 hover:opacity-90 transition-opacity disabled:opacity-60
                                 flex items-center justify-center gap-2 cursor-pointer"
                    >
                      {loading
                        ? <><Loader2 className="w-4 h-4 animate-spin"/> Sending...</>
                        : "Send Reset Email"}
                    </button>
                  </form>
                )}
              </motion.div>

            ) : tab === "signin" ? (

              /* ── SIGN IN VIEW ── */
              <motion.div key="signin"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="text-2xl font-extrabold text-[#111] tracking-tight mb-1">
                  Welcome back
                </h2>
                <p className="text-[13px] text-[#888] mb-6">
                  Sign in to your account to continue
                </p>

                <AnimatePresence>
                  <ErrorBanner message={error} onClose={clearError} />
                </AnimatePresence>

                {/* Google button */}
                <button
                  type="button"
                  onClick={handleGoogle}
                  disabled={gLoading || loading}
                  className="w-full flex items-center justify-center gap-2.5 py-3
                             border-[1.5px] border-[#E8E4FF] rounded-xl text-[13px]
                             font-semibold text-[#333] hover:border-[#6B5CE7]
                             hover:bg-[#F8F7FF] transition-all bg-white mb-5
                             disabled:opacity-60 disabled:cursor-not-allowed
                             cursor-pointer"
                >
                  {gLoading
                    ? <Loader2 className="w-4 h-4 animate-spin text-[#6B5CE7]"/>
                    : GOOGLE_ICON
                  }
                  {gLoading ? "Opening Google..." : "Continue with Google"}
                </button>

                <div className="flex items-center gap-3 mb-5">
                  <div className="flex-1 h-px bg-[#F0EEFF]"/>
                  <span className="text-[11px] text-[#BBB] font-medium whitespace-nowrap">
                    or with email
                  </span>
                  <div className="flex-1 h-px bg-[#F0EEFF]"/>
                </div>

                <form onSubmit={handleSignIn} noValidate>
                  <div className="space-y-4 mb-2">
                    <div>
                      <label className={labelClass}>Email address</label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type="email"
                          placeholder="you@example.com"
                          className={inputClass}
                          value={form.email}
                          onChange={e => upd("email", e.target.value)}
                        />
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Password</label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type={showPass ? "text" : "password"}
                          placeholder="••••••••"
                          className={`${inputClass} pr-10`}
                          value={form.password}
                          onChange={e => upd("password", e.target.value)}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass(s => !s)}
                          className="absolute right-3 top-1/2 -translate-y-1/2
                                     text-[#CCC] hover:text-[#6B5CE7] transition-colors cursor-pointer"
                        >
                          {showPass
                            ? <EyeOff className="w-4 h-4"/>
                            : <Eye className="w-4 h-4"/>}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end mb-5">
                    <button
                      type="button"
                      onClick={() => { setShowReset(true); clearError(); }}
                      className="text-[11px] text-[#6B5CE7] font-semibold
                                 hover:underline cursor-pointer"
                    >
                      Forgot password?
                    </button>
                  </div>

                  <button
                    type="submit"
                    disabled={loading || gLoading}
                    className="w-full py-3 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                               rounded-xl text-[14px] font-bold text-white
                               hover:opacity-90 transition-opacity
                               disabled:opacity-60 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {loading
                      ? <><Loader2 className="w-4 h-4 animate-spin"/> Signing in...</>
                      : "Sign In →"}
                  </button>
                </form>

                <p className="text-center text-[12px] text-[#888] mt-5">
                  Don't have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchTab("register")}
                    className="text-[#6B5CE7] font-semibold hover:underline cursor-pointer"
                  >
                    Create one free
                  </button>
                </p>
              </motion.div>

            ) : (

              /* ── REGISTER VIEW ── */
              <motion.div key="register"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="text-2xl font-extrabold text-[#111] tracking-tight mb-1">
                  Create account
                </h2>
                <p className="text-[13px] text-[#888] mb-6">
                  Start your AI career journey — completely free
                </p>

                <AnimatePresence>
                  <ErrorBanner message={error} onClose={clearError} />
                </AnimatePresence>

                {/* Google button */}
                <button
                  type="button"
                  onClick={handleGoogle}
                  disabled={gLoading || loading}
                  className="w-full flex items-center justify-center gap-2.5 py-3
                             border-[1.5px] border-[#E8E4FF] rounded-xl text-[13px]
                             font-semibold text-[#333] hover:border-[#6B5CE7]
                             hover:bg-[#F8F7FF] transition-all bg-white mb-5
                             disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                >
                  {gLoading
                    ? <Loader2 className="w-4 h-4 animate-spin text-[#6B5CE7]"/>
                    : GOOGLE_ICON
                  }
                  {gLoading ? "Opening Google..." : "Continue with Google"}
                </button>

                <div className="flex items-center gap-3 mb-5">
                  <div className="flex-1 h-px bg-[#F0EEFF]"/>
                  <span className="text-[11px] text-[#BBB] font-medium whitespace-nowrap">
                    or with email
                  </span>
                  <div className="flex-1 h-px bg-[#F0EEFF]"/>
                </div>

                <form onSubmit={handleRegister} noValidate>
                  <div className="space-y-4 mb-5">
                    <div>
                      <label className={labelClass}>Full name</label>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type="text"
                          placeholder="Vedant Bhatt"
                          className={inputClass}
                          value={form.name}
                          onChange={e => upd("name", e.target.value)}
                        />
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Email address</label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type="email"
                          placeholder="you@example.com"
                          className={inputClass}
                          value={form.email}
                          onChange={e => upd("email", e.target.value)}
                        />
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Password</label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type={showPass ? "text" : "password"}
                          placeholder="Min 6 characters"
                          className={`${inputClass} pr-10`}
                          value={form.password}
                          onChange={e => upd("password", e.target.value)}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass(s => !s)}
                          className="absolute right-3 top-1/2 -translate-y-1/2
                                     text-[#CCC] hover:text-[#6B5CE7] transition-colors cursor-pointer"
                        >
                          {showPass
                            ? <EyeOff className="w-4 h-4"/>
                            : <Eye className="w-4 h-4"/>}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Confirm password</label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
                        <input
                          type={showPass2 ? "text" : "password"}
                          placeholder="••••••••"
                          className={`${inputClass} pr-10`}
                          value={form.confirm}
                          onChange={e => upd("confirm", e.target.value)}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass2(s => !s)}
                          className="absolute right-3 top-1/2 -translate-y-1/2
                                     text-[#CCC] hover:text-[#6B5CE7] transition-colors cursor-pointer"
                        >
                          {showPass2
                            ? <EyeOff className="w-4 h-4"/>
                            : <Eye className="w-4 h-4"/>}
                        </button>
                      </div>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading || gLoading}
                    className="w-full py-3 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                               rounded-xl text-[14px] font-bold text-white
                               hover:opacity-90 transition-opacity
                               disabled:opacity-60 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {loading
                      ? <><Loader2 className="w-4 h-4 animate-spin"/> Creating account...</>
                      : "Create Account →"}
                  </button>
                </form>

                <p className="text-center text-[12px] text-[#888] mt-5">
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchTab("signin")}
                    className="text-[#6B5CE7] font-semibold hover:underline cursor-pointer"
                  >
                    Sign in
                  </button>
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ── RIGHT: Purple Brand Panel ── */}
      <div
        className="hidden md:flex relative overflow-hidden items-center justify-center"
        style={{background:"linear-gradient(135deg,#6B5CE7 0%,#8B7CF8 40%,#A78BFA 100%)"}}
      >
        <div className="absolute inset-0 bg-[rgba(80,60,200,0.25)] z-10"/>

        {/* Floating resume cards */}
        {[
          { style:{top:"5%",left:"5%"},   rot:-7,  name:"Vedant Bhatt",  role:"CS Engineer",     label:"ATS SCORE",  val:"85.2",  color:"#6B5CE7", bg:"#E8E4FF" },
          { style:{top:"8%",right:"5%"},  rot:6,   name:"Aryan Kumar",   role:"ML Engineer",     label:"JOB MATCH",  val:"94%",   color:"#E06030", bg:"#FFE4D4" },
          { style:{bottom:"12%",left:"5%"},rot:5,  name:"Sara Mehta",    role:"Product Manager", label:"INTERVIEW",  val:"8.4/10",color:"#2E7D32", bg:"#E8F5E9" },
          { style:{bottom:"8%",right:"4%"},rot:-5, name:"Raj Joshi",     role:"Data Scientist",  label:"FLUENCY",    val:"79/100",color:"#E65100", bg:"#FFF3E0" },
        ].map((card, i) => (
          <motion.div
            key={i}
            className="absolute bg-white rounded-2xl p-3.5 z-20 w-44 shadow-2xl"
            style={{ ...card.style }}
            animate={{
              y:      [0, -7, 0],
              rotate: [card.rot, card.rot + 1.8, card.rot],
            }}
            transition={{
              duration:   3 + i * 0.6,
              repeat:     Infinity,
              ease:       "easeInOut",
              delay:      i * 0.8,
            }}
          >
            <div className="flex items-center gap-2 mb-2.5">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center
                           text-[10px] font-bold shrink-0"
                style={{ background: card.bg, color: card.color }}
              >
                {card.name.split(" ").map(w => w[0]).join("")}
              </div>
              <div>
                <div className="text-[11px] font-bold text-[#111] leading-none">
                  {card.name}
                </div>
                <div className="text-[9px] text-[#888] mt-0.5">{card.role}</div>
              </div>
            </div>
            <div className="h-1.5 rounded-full mb-1.5 bg-[#F0EEFF] overflow-hidden">
              <div className="h-full rounded-full w-3/4"
                style={{ background: card.color }}/>
            </div>
            <div className="h-1.5 rounded-full mb-3 bg-[#F0EEFF] overflow-hidden"
              style={{ width: "55%" }}>
              <div className="h-full rounded-full w-full bg-[#E8E4FF]"/>
            </div>
            <div className="text-[8px] font-bold" style={{ color: card.color }}>
              {card.label}
            </div>
            <div className="text-[18px] font-black text-[#111] tracking-tight leading-tight mt-0.5">
              {card.val}
            </div>
          </motion.div>
        ))}

        {/* Center content */}
        <div className="relative z-20 text-center px-10">
          <div className="flex items-center justify-center gap-3 mb-5">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center border border-white/20"
              style={{ background: "rgba(255,255,255,0.15)" }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L21 7V17L12 22L3 17V7L12 2Z"
                  stroke="white" strokeWidth="1.4" fill="none"/>
                <circle cx="12" cy="12" r="4" fill="white"/>
              </svg>
            </div>
            <span className="text-[24px] font-black text-white tracking-tight">
              CareerMind AI
            </span>
          </div>
          <p
            className="text-[14px] leading-relaxed mb-6 max-w-xs mx-auto"
            style={{ color: "rgba(255,255,255,0.8)" }}
          >
            Upload your resume. Match live jobs.<br/>
            AI rewrite. Voice mock interview.<br/>
            Daily English coach.<br/>
            <strong className="text-white font-bold">
              Everything to land your dream job.
            </strong>
          </p>
          <button
            className="px-6 py-2.5 rounded-full text-[13px] font-semibold
                       text-white border border-white/25 backdrop-blur-md
                       hover:bg-white/20 transition-colors cursor-pointer"
            style={{ background: "rgba(255,255,255,0.15)" }}
          >
            Explore Features →
          </button>
        </div>
      </div>
    </div>
  );
}
