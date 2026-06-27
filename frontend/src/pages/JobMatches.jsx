import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, MapPin, Loader2, AlertCircle, RefreshCw, Briefcase } from "lucide-react";
import api from "../lib/api";
import { useStore } from "../store/useStore";
import JobCard from "../components/JobCard";
import { SkeletonJobCard } from "../components/Skeleton";

export default function JobMatches() {
  const { resume }         = useStore();
  const [query,    setQuery]    = useState("Software Engineer");
  const [location, setLocation] = useState("India");
  const [jobs,     setJobs]     = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const [searched, setSearched] = useState(false);
  const [filter,   setFilter]   = useState("all");

  const fetchJobs = useCallback(async (q, loc) => {
    setLoading(true);
    setError(null);
    setSearched(true);

    // Timeout controller — never hang forever
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => {
      controller.abort();
    }, 20000); // 20 second max

    try {
      const res = await api.get("/jobs", {
        params: {
          q:       q || "Software Engineer",
          location: loc || "India",
          user_id: "anonymous",
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const jobList = res.data?.jobs || res.data || [];

      if (Array.isArray(jobList) && jobList.length > 0) {
        setJobs(jobList);
        setError(null);
      } else {
        setJobs([]);
        setError("No jobs found for this search. Try different keywords.");
      }
    } catch (err) {
      clearTimeout(timeoutId);

      if (err.name === "AbortError" || err.code === "ERR_CANCELED") {
        setError("Search timed out. Your backend may be sleeping — wait 30 seconds and try again.");
      } else if (!err.response) {
        setError(
          `Cannot reach backend at ${import.meta.env.VITE_API_URL || "http://localhost:8000"}. ` +
          "Make sure the backend is running."
        );
      } else if (err.response?.status === 502) {
        setError("Backend server error (502). It may be restarting — wait 30 seconds and try again.");
      } else if (err.response?.status === 503) {
        setError("Backend is starting up. Wait 30 seconds and try again.");
      } else {
        setError(err.userMessage || err.response?.data?.detail || "Search failed. Please try again.");
      }
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-search on page load
  useEffect(() => {
    fetchJobs(query, location);
  }, []);

  const handleSearch = (e) => {
    e?.preventDefault();
    fetchJobs(query, location);
  };

  const filteredJobs = jobs.filter(job => {
    if (filter === "strong") return (job.match_score || 0) >= 70;
    if (filter === "partial") return (job.match_score || 0) < 70;
    return true;
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-6xl mx-auto px-6 py-8"
    >
      {/* Header */}
      <div className="mb-6">
        <div className="text-xs font-bold text-[#6B5CE7] tracking-widest mb-1">STEP 02</div>
        <h1 className="text-3xl font-extrabold text-[#111] tracking-tight">
          Job <span className="text-[#6B5CE7]">Matches</span>
        </h1>
        <p className="text-[#888] text-sm mt-1">
          Find roles that match your skills and get an AI-scored fit report.
        </p>
      </div>

      {/* Search Bar */}
      <div className="bg-white border border-[#E8E4FF] rounded-2xl p-4 mb-6
                      shadow-[0_2px_12px_rgba(107,92,231,0.06)]">
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Job title, role, or keyword"
              className="w-full pl-10 pr-4 py-2.5 border-[1.5px] border-[#E8E4FF]
                         rounded-xl text-[13px] text-[#111] bg-[#FAFAFA] outline-none
                         focus:border-[#6B5CE7] focus:bg-white transition-all"
            />
          </div>
          <div className="relative w-44">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#CCC]"/>
            <input
              type="text"
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder="Location"
              className="w-full pl-10 pr-4 py-2.5 border-[1.5px] border-[#E8E4FF]
                         rounded-xl text-[13px] text-[#111] bg-[#FAFAFA] outline-none
                         focus:border-[#6B5CE7] focus:bg-white transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r
                       from-[#6B5CE7] to-[#8B7CF8] rounded-xl text-[13px] font-bold
                       text-white hover:opacity-90 transition-opacity
                       disabled:opacity-70 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin"/> Searching...</>
              : <><Search className="w-4 h-4"/> Search Jobs</>
            }
          </button>
        </form>

        {/* Filter tabs */}
        {jobs.length > 0 && (
          <div className="flex gap-2 mt-3 pt-3 border-t border-[#F0EEFF]">
            {[
              { key: "all",     label: `All (${jobs.length})` },
              { key: "strong",  label: `Strong Match (${jobs.filter(j => (j.match_score||0) >= 70).length})` },
              { key: "partial", label: `Partial Match (${jobs.filter(j => (j.match_score||0) < 70).length})` },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  filter === tab.key
                    ? "bg-[#6B5CE7] text-white"
                    : "bg-[#F0EEFF] text-[#6B5CE7] hover:bg-[#E8E4FF]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ERROR STATE — never show empty skeletons */}
      {error && !loading && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white border border-[#E8E4FF] rounded-2xl p-8 text-center
                     shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
        >
          <div className="w-14 h-14 bg-red-50 rounded-full flex items-center
                          justify-center mx-auto mb-4">
            <AlertCircle className="w-7 h-7 text-red-400"/>
          </div>
          <h3 className="text-[15px] font-bold text-[#111] mb-2">
            Search failed
          </h3>
          <p className="text-[13px] text-[#888] mb-5 max-w-md mx-auto leading-relaxed">
            {error}
          </p>

          {/* Show demo jobs when backend unreachable */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={() => fetchJobs(query, location)}
              className="flex items-center justify-center gap-2 px-5 py-2.5
                         bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                         rounded-xl text-[13px] font-bold text-white
                         hover:opacity-90 transition-opacity"
            >
              <RefreshCw className="w-4 h-4"/> Try Again
            </button>
            <button
              onClick={() => {
                setError(null);
                setJobs(getDemoJobs(query));
              }}
              className="flex items-center justify-center gap-2 px-5 py-2.5
                         bg-white border border-[#E8E4FF] rounded-xl
                         text-[13px] font-semibold text-[#6B5CE7]
                         hover:bg-[#F0EEFF] transition-colors"
            >
              <Briefcase className="w-4 h-4"/> Show Demo Jobs
            </button>
          </div>
        </motion.div>
      )}

      {/* LOADING SKELETONS */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonJobCard key={i}/>
          ))}
        </div>
      )}

      {/* JOB CARDS */}
      {!loading && !error && filteredJobs.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence>
            {filteredJobs.map((job, i) => (
              <motion.div
                key={job.id || i}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <JobCard job={job}/>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* EMPTY STATE */}
      {!loading && !error && searched && filteredJobs.length === 0 && (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">🔍</div>
          <h3 className="text-[15px] font-bold text-[#111] mb-2">No jobs found</h3>
          <p className="text-[13px] text-[#888]">
            Try different keywords or location
          </p>
        </div>
      )}
    </motion.div>
  );
}

// Demo jobs shown when backend is unreachable
function getDemoJobs(query) {
  return [
    {
      id: "demo1",
      title: `Senior ${query}`,
      company: "TechCorp India",
      location: "Bangalore, India",
      description: `We are hiring a Senior ${query} with 3+ years experience in Python, React, and FastAPI. Strong problem-solving skills required.`,
      apply_link: "#",
      salary: "12-20 LPA",
      source: "demo",
      match_score: 88,
      matched_skills: ["Python", "React", "FastAPI"],
      missing_skills: ["Docker"],
      recommendation: "Strong match based on your profile",
    },
    {
      id: "demo2",
      title: `AI/ML ${query}`,
      company: "InnovateTech",
      location: "Hyderabad, India",
      description: `AI-focused ${query} role. LangChain, Gemini, RAG, vector databases, FastAPI. 0-2 years experience welcome.`,
      apply_link: "#",
      salary: "8-15 LPA",
      source: "demo",
      match_score: 92,
      matched_skills: ["LangChain", "Python", "FastAPI", "React"],
      missing_skills: ["Kubernetes"],
      recommendation: "Excellent match — your AI skills align perfectly",
    },
    {
      id: "demo3",
      title: `Full Stack ${query}`,
      company: "GlobalTech Solutions",
      location: "Remote, India",
      description: `Remote Full Stack ${query} position. React, Node.js, Python, Docker, AWS. Flexible hours, great culture.`,
      apply_link: "#",
      salary: "10-18 LPA",
      source: "demo",
      match_score: 78,
      matched_skills: ["React", "Python", "Node.js"],
      missing_skills: ["AWS", "Docker"],
      recommendation: "Good match — consider learning AWS",
    },
    {
      id: "demo4",
      title: `Junior ${query}`,
      company: "StartupXYZ",
      location: "Mumbai, India",
      description: `Junior ${query} role for fresh graduates. React, Python, Firebase, MongoDB. Mentorship provided.`,
      apply_link: "#",
      salary: "4-8 LPA",
      source: "demo",
      match_score: 82,
      matched_skills: ["React", "Python", "Firebase", "MongoDB"],
      missing_skills: [],
      recommendation: "Great entry-level opportunity matching your stack",
    },
    {
      id: "demo5",
      title: `${query} Intern`,
      company: "MNC Corp",
      location: "Pune, India",
      description: `${query} internship for CS students. Python, JavaScript, REST APIs, Git. 6-month paid internship.`,
      apply_link: "#",
      salary: "15,000-25,000/month",
      source: "demo",
      match_score: 75,
      matched_skills: ["Python", "JavaScript", "Git"],
      missing_skills: ["System Design"],
      recommendation: "Good match for your current experience level",
    },
    {
      id: "demo6",
      title: `${query} Engineer`,
      company: "Product Studio",
      location: "Ahmedabad, India",
      description: `${query} Engineer at a growing product company. TypeScript, React, Node.js, PostgreSQL. Equity offered.`,
      apply_link: "#",
      salary: "6-12 LPA",
      source: "demo",
      match_score: 70,
      matched_skills: ["TypeScript", "React"],
      missing_skills: ["PostgreSQL", "Node.js"],
      recommendation: "Decent match — strong React skills are valued here",
    },
  ];
}
