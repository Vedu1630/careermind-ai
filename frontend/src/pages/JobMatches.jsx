import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Search, MapPin, Filter, Loader2, RefreshCw, AlertCircle, Briefcase } from 'lucide-react'
import useStore from '../store/useStore'
import { fetchJobs, getUserId } from '../lib/api'
import JobCard from '../components/JobCard'

const FILTERS = ['All', 'Strong Match', 'Partial Match', 'Weak Match']
const FIT_MAP = { 'Strong Match': 'strong', 'Partial Match': 'partial', 'Weak Match': 'weak' }

export default function JobMatches() {
  const navigate = useNavigate()
  const { jobs, setJobListings, setJobSearch, setJobsLoading, setSelectedJob, resume } = useStore()

  const [query, setQuery] = useState(jobs.query || 'Software Engineer')
  const [location, setLocation] = useState(jobs.location || 'United States')
  const [activeFilter, setActiveFilter] = useState('All')
  const [error, setError] = useState('')

  const handleSearch = useCallback(async () => {
    setError('')
    setJobsLoading(true)
    setJobSearch(query, location)
    try {
      const userId = getUserId()
      const data = await fetchJobs({ query, location, userId })
      setJobListings(data.jobs || [])
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to fetch jobs. Please try again.')
    } finally {
      setJobsLoading(false)
    }
  }, [query, location, setJobListings, setJobSearch, setJobsLoading])

  const handleRewrite = useCallback((scoredJob) => {
    setSelectedJob(scoredJob.job)
    navigate('/rewrite')
  }, [setSelectedJob, navigate])

  // Filter jobs
  const filteredJobs = jobs.listings.filter((j) => {
    if (activeFilter === 'All') return true
    return j.fit_level === FIT_MAP[activeFilter]
  })

  const strongCount = jobs.listings.filter((j) => j.fit_level === 'strong').length
  const partialCount = jobs.listings.filter((j) => j.fit_level === 'partial').length

  return (
    <div className="page-container py-10">
      <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        {/* Header */}
        <div className="mb-8">
          <p className="section-label mb-2 text-[#6B5CE7] uppercase text-[11px] tracking-wider font-semibold">Step 02</p>
          <h1 className="font-sans font-extrabold text-3xl sm:text-4xl text-[#111111] mb-2">
            Job <span className="text-gradient">Matches</span>
          </h1>
          <p className="text-[#555555]">Find roles that match your skills and get an AI-scored fit report.</p>
        </div>

        {/* Search bar */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-6 bg-white border border-[#E8E4FF] rounded-2xl mb-6 shadow-sm"
        >
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#888888]" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Job title or keywords..."
                className="input-field pl-10 bg-[#FAFAFA] border border-[#E8E4FF] rounded-xl text-[#111111] h-12 w-full focus:outline-none focus:border-[#6B5CE7] transition-all"
                id="job-search-query"
              />
            </div>
            <div className="relative sm:w-60">
              <MapPin size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#888888]" />
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Location..."
                className="input-field pl-10 bg-[#FAFAFA] border border-[#E8E4FF] rounded-xl text-[#111111] h-12 w-full focus:outline-none focus:border-[#6B5CE7] transition-all"
                id="job-search-location"
              />
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSearch}
              disabled={jobs.isLoading}
              className="btn-primary px-6 h-12 rounded-xl whitespace-nowrap flex items-center justify-center gap-2 font-semibold"
            >
              {jobs.isLoading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Search size={18} />
              )}
              {jobs.isLoading ? 'Searching...' : 'Search'}
            </motion.button>
          </div>

          {!resume.analysis && (
            <p className="mt-3.5 text-xs text-[#D97706] flex items-center gap-1.5 font-medium">
              <AlertCircle size={14} />
              Tip: Analyze your resume first for AI-powered match scoring.
            </p>
          )}
        </motion.div>

        {/* Error */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="mb-6 flex items-center gap-2 p-4 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#EF4444] text-sm font-medium"
          >
            <AlertCircle size={16} /> {error}
          </motion.div>
        )}

        {/* Filter tabs + count */}
        {jobs.listings.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col sm:flex-row sm:items-center gap-4 mb-6"
          >
            <div className="flex gap-2 flex-wrap">
              {FILTERS.map((f) => (
                <motion.button
                  key={f}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setActiveFilter(f)}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer ${
                    activeFilter === f
                      ? 'text-white bg-[#6B5CE7] border border-[#6B5CE7] shadow-sm'
                      : 'text-[#555555] bg-white border border-[#E8E4FF] hover:text-[#111111] hover:bg-[#F0EEFF]'
                  }`}
                >
                  {f}
                </motion.button>
              ))}
            </div>
            <div className="flex gap-3 text-xs sm:ml-auto font-semibold">
              <span className="text-[#16A34A] bg-[#DCFCE7] px-2 py-1 rounded-md">{strongCount} strong</span>
              <span className="text-[#D97706] bg-[#FEF3C7] px-2 py-1 rounded-md">{partialCount} partial</span>
              <span className="text-[#888888] bg-[#F0EEFF] px-2 py-1 rounded-md">{jobs.listings.length - strongCount - partialCount} weak</span>
            </div>
          </motion.div>
        )}

        {/* Job grid */}
        {jobs.isLoading ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="card h-72 shimmer bg-white border border-[#E8E4FF] rounded-2xl" />
            ))}
          </div>
        ) : filteredJobs.length > 0 ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <AnimatePresence>
              {filteredJobs.map((scoredJob, i) => (
                <JobCard
                  key={scoredJob.job?.id || i}
                  scoredJob={scoredJob}
                  onRewrite={handleRewrite}
                  delay={i * 0.05}
                />
              ))}
            </AnimatePresence>
          </div>
        ) : jobs.listings.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="card p-16 text-center bg-white border border-[#E8E4FF] rounded-2xl shadow-sm"
          >
            <Briefcase size={48} className="text-[#888888] mx-auto mb-4" />
            <h2 className="font-sans font-bold text-xl text-[#111111] mb-2">No jobs loaded yet</h2>
            <p className="text-sm text-[#555555] mb-6 max-w-sm mx-auto">Search for a job title above to see real-time matches scored by our AI against your profile.</p>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={handleSearch}
              className="btn-primary inline-flex items-center gap-2"
            >
              <Search size={16} /> Search Now
            </motion.button>
          </motion.div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-12 text-center bg-white border border-[#E8E4FF] rounded-2xl shadow-sm">
            <Filter size={36} className="text-[#888888] mx-auto mb-3" />
            <p className="text-sm text-[#555555]">No jobs match the selected filter.</p>
            <button onClick={() => setActiveFilter('All')} className="btn-ghost mt-4 text-sm text-[#6B5CE7] hover:bg-[#F0EEFF] px-4 py-2 rounded-xl inline-flex items-center gap-1.5 font-semibold">
              <RefreshCw size={14} /> Show all
            </button>
          </motion.div>
        )}
      </motion.div>
    </div>
  )
}
