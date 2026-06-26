/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        base: '#F0EEFF',
        'primary': {
          DEFAULT: '#6B5CE7',
          light: '#8B7CF8',
          pale: '#E8E4FF',
        },
        border: {
          DEFAULT: '#E8E4FF',
          soft: '#F0EEFF',
        },
        success: {
          DEFAULT: '#22C55E',
          light: '#DCFCE7',
        },
        warning: {
          DEFAULT: '#F59E0B',
          light: '#FEF3C7',
        },
        danger: {
          DEFAULT: '#EF4444',
          light: '#FEE2E2',
        },
        info: {
          DEFAULT: '#3B82F6',
        },
        text: {
          primary: '#111111',
          secondary: '#555555',
          muted: '#888888',
          faint: '#BBBBBB',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        'card': '0 2px 12px rgba(0,0,0,0.06)',
        'purple': '0 4px 20px rgba(107,92,231,0.12)',
        'purple-lg': '0 8px 40px rgba(107,92,231,0.16)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
