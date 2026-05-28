/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#0B0D19', // Sleek deep space blue
        card: '#131930',       // Dark glass base card
        primary: {
          DEFAULT: '#6D28D9',  // Violet glow primary
          hover: '#7C3AED',
        },
        accent: '#10B981',     // Success green accent
      },
    },
  },
  plugins: [],
}
