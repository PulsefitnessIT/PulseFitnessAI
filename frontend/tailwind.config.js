/** @type {import('tailwindcss').Config} */
// Pulse Fitness brand hue-collapse — every legacy accent hue (blue/sky/cyan/
// indigo/violet/purple/teal) maps to ONE Core-Blue (#19CDFF) scale so the whole
// app renders strictly on-brand. Off-brand navy/violet/indigo can no longer appear.
const PULSE_ACCENT = {
  50: '#e4f9ff', 100: '#cff1ff', 200: '#9ce4ff', 300: '#5cd3ff', 400: '#19CDFF',
  500: '#00b8f0', 600: '#0091ca', 700: '#0073a4', 800: '#00608b', 900: '#044f74', 950: '#033350',
};
module.exports = {
    // Activate `dark:` variants when the *nearest* themed ancestor is dark.
    // The :not() guards cancel the variant inside any subtree that explicitly
    // re-themes to light (`data-theme="light"` or class="light"), so pages
    // that force one theme don't accidentally trigger the opposite-mode
    // text/bg classes (the recurring "dark on light" / "light on dark" bug).
    darkMode: ["variant", [
      "&:is(.dark *):not(:is([data-theme=\"light\"] *)):not(:is(.light *))",
      "&:is([data-theme=\"dark\"] *):not(:is([data-theme=\"light\"] *)):not(:is(.light *))",
    ]],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
        extend: {
                borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)'
                },
                colors: {
                        blue: PULSE_ACCENT,
                        sky: PULSE_ACCENT,
                        cyan: PULSE_ACCENT,
                        indigo: PULSE_ACCENT,
                        violet: PULSE_ACCENT,
                        purple: PULSE_ACCENT,
                        teal: PULSE_ACCENT,
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        card: {
                                DEFAULT: 'hsl(var(--card))',
                                foreground: 'hsl(var(--card-foreground))'
                        },
                        popover: {
                                DEFAULT: 'hsl(var(--popover))',
                                foreground: 'hsl(var(--popover-foreground))'
                        },
                        primary: {
                                DEFAULT: 'hsl(var(--primary))',
                                foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                                DEFAULT: 'hsl(var(--secondary))',
                                foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                                DEFAULT: 'hsl(var(--muted))',
                                foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                                DEFAULT: 'hsl(var(--accent))',
                                foreground: 'hsl(var(--accent-foreground))'
                        },
                        destructive: {
                                DEFAULT: 'hsl(var(--destructive))',
                                foreground: 'hsl(var(--destructive-foreground))'
                        },
                        border: 'hsl(var(--border))',
                        input: 'hsl(var(--input))',
                        ring: 'hsl(var(--ring))',
                        chart: {
                                '1': 'hsl(var(--chart-1))',
                                '2': 'hsl(var(--chart-2))',
                                '3': 'hsl(var(--chart-3))',
                                '4': 'hsl(var(--chart-4))',
                                '5': 'hsl(var(--chart-5))'
                        }
                },
                keyframes: {
                        'accordion-down': {
                                from: {
                                        height: '0'
                                },
                                to: {
                                        height: 'var(--radix-accordion-content-height)'
                                }
                        },
                        'accordion-up': {
                                from: {
                                        height: 'var(--radix-accordion-content-height)'
                                },
                                to: {
                                        height: '0'
                                }
                        }
                },
                animation: {
                        'accordion-down': 'accordion-down 0.2s ease-out',
                        'accordion-up': 'accordion-up 0.2s ease-out'
                }
        }
  },
  plugins: [require("tailwindcss-animate")],
};