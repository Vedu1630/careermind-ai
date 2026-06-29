import { Component } from 'react'

/**
 * ErrorBoundary — catches render‑time errors so the whole page
 * doesn't go white.  Shows a styled fallback + retry button.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info?.componentStack)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[300px] flex flex-col items-center justify-center p-8">
          <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-8 max-w-md text-center">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-[#FEE2E2] flex items-center justify-center">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h2 className="font-sans font-bold text-lg text-[#111] mb-2">
              Something went wrong
            </h2>
            <p className="text-sm text-[#555] mb-4">
              {this.state.error?.message || 'An unexpected error occurred while rendering this section.'}
            </p>
            <button
              onClick={this.handleRetry}
              className="px-5 py-2.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity cursor-pointer"
            >
              Try Again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
