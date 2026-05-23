/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ops: {
          bg:               '#f4f7fb',
          surface:          '#ffffff',
          card:             '#ffffff',
          'card-hover':     '#fafbfc',
          border:           '#e2e8f0',
          'border-focus':   '#bfdbfe',
          accent:           '#0ea5e9',
          'accent-light':   '#e0f2fe',
          now:              '#ef4444',
          'now-light':      '#fef2f2',
          success:          '#059669',
          'success-light':  '#ecfdf5',
          warning:          '#d97706',
          'warning-light':  '#fffbeb',
          danger:           '#dc2626',
          'danger-light':   '#fef2f2',
          info:             '#2563eb',
          'info-light':     '#eff6ff',
          'text-primary':   '#0f172a',
          'text-secondary': '#475569',
          'text-muted':     '#94a3b8',
          'text-disabled':  '#cbd5e1',
        },
      },
      fontFamily: {
        sans: ['IBM Plex Sans Thai', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', { lineHeight: '14px' }],
      },
      animation: {
        blink:           'blink 1.1s step-end infinite',
        'fade-in':       'fadeIn 0.25s ease-out',
        'slide-down':    'slideDown 0.2s ease-out',
        'expand':        'expand 0.28s cubic-bezier(0.16,1,0.3,1)',
        'shake':         'shake 0.4s ease-in-out',
        'slide-in-right':'slideInRight 0.25s ease-out',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideDown: {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        expand: {
          from: { opacity: '0', transform: 'scaleY(0.96) translateY(-6px)' },
          to:   { opacity: '1', transform: 'scaleY(1)    translateY(0)' },
        },
        slideInRight: {
          from: { opacity: '0', transform: 'translateX(16px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '20%':      { transform: 'translateX(-8px)' },
          '40%':      { transform: 'translateX(8px)' },
          '60%':      { transform: 'translateX(-6px)' },
          '80%':      { transform: 'translateX(6px)' },
        },
      },
      boxShadow: {
        card:         '0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04)',
        'card-md':    '0 4px 12px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04)',
        'card-active':'0 0 0 2px rgba(14,165,233,0.3), 0 4px 20px rgba(14,165,233,0.15), 0 1px 4px rgba(14,165,233,0.1)',
        'now':        '0 0 0 3px rgba(239,68,68,0.15), 0 0 10px rgba(239,68,68,0.25)',
        'focus':      '0 0 0 3px rgba(14,165,233,0.2)',
        'header':     '0 1px 3px rgba(15,23,42,0.06)',
      },
    },
  },
  plugins: [],
}
