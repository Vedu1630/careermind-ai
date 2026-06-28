import { create } from 'zustand'
import { persist, devtools } from 'zustand/middleware'

const useStore = create(
  devtools(
    persist(
      (set, get) => ({
        // ── Resume slice ──────────────────────────────────────────────────
        resume: {
          path: null,
          filename: null,
          text: '',
          analysis: null,
        },
        setResumePath: (path, filename) =>
          set((s) => ({ resume: { ...s.resume, path, filename } })),
        setResumeAnalysis: (analysis) =>
          set((s) => ({
            resume: {
              ...s.resume,
              analysis,
              text: analysis?.resume_text || s.resume.text,
            },
          })),
        clearResume: () =>
          set(() => ({
            resume: { path: null, filename: null, text: '', analysis: null },
          })),

        // ── Jobs slice ────────────────────────────────────────────────────
        jobs: {
          listings: [],
          selectedJob: null,
          query: 'Software Engineer',
          location: 'United States',
          isLoading: false,
        },
        setJobListings: (listings) =>
          set((s) => ({ jobs: { ...s.jobs, listings } })),
        setSelectedJob: (job) =>
          set((s) => ({ jobs: { ...s.jobs, selectedJob: job } })),
        setJobSearch: (query, location) =>
          set((s) => ({ jobs: { ...s.jobs, query, location } })),
        setJobsLoading: (isLoading) =>
          set((s) => ({ jobs: { ...s.jobs, isLoading } })),
        clearJobs: () =>
          set(() => ({
            jobs: {
              listings: [],
              selectedJob: null,
              query: 'Software Engineer',
              location: 'United States',
              isLoading: false,
            },
          })),

        // ── Rewrite slice ─────────────────────────────────────────────────
        rewrite: {
          original: '',
          rewritten: '',
          changesSummary: [],
          keywordsAdded: [],
          atsScores: null,
          rewrittenPdfPath: null,
          isLoading: false,
        },
        setRewriteResult: (data) =>
          set(() => ({
            rewrite: {
              original: data.original || data.original_text || '',
              rewritten: data.rewritten || data.rewritten_text || '',
              changesSummary: data.changes_summary || [],
              keywordsAdded: data.keywords_added || [],
              atsScores: data.ats_scores || null,
              rewrittenPdfPath: data.rewritten_pdf_path || null,
              isLoading: false,
            },
          })),
        setRewriteLoading: (isLoading) =>
          set((s) => ({ rewrite: { ...s.rewrite, isLoading } })),
        clearRewrite: () =>
          set(() => ({
            rewrite: {
              original: '',
              rewritten: '',
              changesSummary: [],
              keywordsAdded: [],
              atsScores: null,
              rewrittenPdfPath: null,
              isLoading: false,
            },
          })),

        // ── Interview slice ───────────────────────────────────────────────
        interview: {
          history: [],
          currentQuestion: null,
          currentAudioB64: null,
          roundNumber: 1,
          scores: [],
          jobTitle: '',
          isLoading: false,
        },
        setInterviewJobTitle: (jobTitle) =>
          set((s) => ({ interview: { ...s.interview, jobTitle } })),
        setCurrentQuestion: (question, audioB64) =>
          set((s) => ({
            interview: {
              ...s.interview,
              currentQuestion: question,
              currentAudioB64: audioB64 || null,
            },
          })),
        addInterviewResult: (questionData) =>
          set((s) => {
            const newHistory = [...s.interview.history, questionData]
            const newScores = [...s.interview.scores, questionData.score]
            return {
              interview: {
                ...s.interview,
                history: newHistory,
                scores: newScores,
                roundNumber: s.interview.roundNumber + 1,
                currentQuestion: null,
              },
            }
          }),
        setInterviewLoading: (isLoading) =>
          set((s) => ({ interview: { ...s.interview, isLoading } })),
        resetInterview: () =>
          set((s) => ({
            interview: {
              history: [],
              currentQuestion: null,
              currentAudioB64: null,
              roundNumber: 1,
              scores: [],
              jobTitle: s.interview.jobTitle,
              isLoading: false,
            },
          })),

        // ── Agent activity slice ──────────────────────────────────────────
        agent: {
          events: [],
          isActive: false,
          isConnected: false,
        },
        addAgentEvent: (event) =>
          set((s) => ({
            agent: {
              ...s.agent,
              events: [
                ...s.agent.events.slice(-49), // Keep last 50 events
                { ...event, id: Date.now() + Math.random() },
              ],
              isActive: event.status !== 'done' && event.status !== 'error',
            },
          })),
        setAgentConnected: (isConnected) =>
          set((s) => ({ agent: { ...s.agent, isConnected } })),
        clearAgentEvents: () =>
          set((s) => ({ agent: { ...s.agent, events: [], isActive: false } })),

        // ── Auth slice ────────────────────────────────────────────────────
        auth: {
          userId: null,
          token: null,
        },
        setAuth: (userId, token) =>
          set(() => ({ auth: { userId, token } })),
        clearAuth: () =>
          set(() => ({ auth: { userId: null, token: null } })),
      }),
      {
        name: 'careermind-store',
        partialize: (state) => ({
          auth: state.auth,
          resume: { path: state.resume.path, filename: state.resume.filename },
          jobs: { query: state.jobs.query, location: state.jobs.location, selectedJob: state.jobs.selectedJob },
          interview: { jobTitle: state.interview.jobTitle, roundNumber: state.interview.roundNumber },
        }),
        merge: (persistedState, currentState) => {
          if (!persistedState) return currentState
          return {
            ...currentState,
            ...persistedState,
            auth: {
              ...currentState.auth,
              ...(persistedState.auth || {}),
            },
            resume: {
              ...currentState.resume,
              ...(persistedState.resume || {}),
            },
            jobs: {
              ...currentState.jobs,
              ...(persistedState.jobs || {}),
            },
            interview: {
              ...currentState.interview,
              ...(persistedState.interview || {}),
            },
          }
        },
      }
    ),
    { name: 'CareerMind AI Store' }
  )
)

export { useStore }
export default useStore
