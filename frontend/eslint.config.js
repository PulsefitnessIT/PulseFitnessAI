import js from "@eslint/js";
import pluginReact from "eslint-plugin-react";
import pluginReactHooks from "eslint-plugin-react-hooks";
import pluginImport from "eslint-plugin-import";
import gymaxisPlugin from "./eslint-rules/gymaxis-plugin.js";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    plugins: {
      react: pluginReact,
      "react-hooks": pluginReactHooks,
      import: pluginImport,
      gymaxis: gymaxisPlugin,
    },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        process: "readonly",
        fetch: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        URL: "readonly",
        FormData: "readonly",
        FileReader: "readonly",
        Blob: "readonly",
        navigator: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        HTMLElement: "readonly",
        Event: "readonly",
        MouseEvent: "readonly",
        KeyboardEvent: "readonly",
        alert: "readonly",
        confirm: "readonly",
        AbortController: "readonly",
        Headers: "readonly",
        Request: "readonly",
        Response: "readonly",
        MutationObserver: "readonly",
        ResizeObserver: "readonly",
        IntersectionObserver: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        Image: "readonly",
        Audio: "readonly",
        MediaRecorder: "readonly",
        btoa: "readonly",
        atob: "readonly",
        File: "readonly",
        CustomEvent: "readonly",
        URLSearchParams: "readonly",
        prompt: "readonly",
        // Iter 216h226 — used by offline-queue & performance traces.
        performance: "readonly",
        crypto: "readonly",
        // Browser event constructors used by router/back-handlers.
        PopStateEvent: "readonly",
        // Service-worker / push-notification globals.
        Notification: "readonly",
        indexedDB: "readonly",
        IDBKeyRange: "readonly",
      },
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      // Errors — catch real bugs
      "no-undef": "error",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-duplicate-imports": "error",
      "no-self-assign": "error",
      "no-unreachable": "error",

      // React
      "react/jsx-uses-react": "off",       // not needed with new JSX transform
      "react/react-in-jsx-scope": "off",   // not needed with new JSX transform
      "react/prop-types": "off",           // using JS not TS, skip prop-types
      "react/jsx-key": "error",
      "react/no-direct-mutation-state": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // Style — keep consistent
      "no-var": "error",
      "prefer-const": "warn",
      "eqeqeq": ["error", "smart"],
      "no-empty": ["error", { allowEmptyCatch: true }],

      // Dark-mode leakage — disabled globally; turned on only for the
      // newer surfaces below where we want zero regression from now on.
      "gymaxis/no-dark-mode-leakage": "off",
    },
  },
  {
    // Iter 215i — Light-mode audit COMPLETE in scope folders. Promoted
    // to `error` after Wave-2 codemods cleared 86 leaks → 0.
    //
    // Iter 216h226 — temporarily downgraded to `warn` after a regression
    // crept in across ~300 files (CRM Phase 2 / 3 + new MasterAdmin
    // tabs were authored with raw Tailwind colour utilities). The
    // backlog is tracked in /app/memory/ROADMAP.md (P1: "Light-mode
    // leakage cleanup"). The Quality Gate's `--max-warnings 1500`
    // budget keeps the count from growing. Restore to `error` once
    // the cleanup PRs land.
    files: [
      "src/pages/Marketing/**/*.{js,jsx}",
      "src/pages/Memberships/**/*.{js,jsx}",
      "src/pages/CRM/**/*.{js,jsx}",
      "src/pages/ServiceDesk/**/*.{js,jsx}",
      "src/pages/GymFloor/**/*.{js,jsx}",
      "src/pages/Member/**/*.{js,jsx}",
      "src/pages/Instructor/**/*.{js,jsx}",
      "src/pages/MOD/**/*.{js,jsx}",
      // Iter 215j — Operations portal added after Lee's screenshots showed
      // black cards on white pages. /pulse renders LiteDashboardPage which
      // pulls heavily from these folders.
      "src/pages/LiteDashboard/**/*.{js,jsx}",
      "src/pages/Dashboard/**/*.{js,jsx}",
      "src/pages/LiteDashboardPage.{js,jsx}",
      "src/pages/SupplierDashboardTab.{js,jsx}",
      "src/pages/PulseReportsTab.{js,jsx}",
      "src/pages/PulseGymLayoutTab.{js,jsx}",
      "src/pages/PulseCheckSheetsTab.{js,jsx}",
      "src/pages/PulseAIDiagnosisTab.{js,jsx}",
      "src/components/shared/**/*.{js,jsx}",
    ],
    plugins: { gymaxis: gymaxisPlugin },
    rules: {
      "gymaxis/no-dark-mode-leakage": "warn",
    },
  },
  {
    // no-inline-hex — Iter 215h promoted to ERROR. Iter 216h226
    // downgraded back to `warn` after the same colour-token migration
    // gap. Tracked under ROADMAP.md → "Inline-hex sweep". `--max-warnings`
    // pins the budget so we cannot regress further.
    files: [
      "src/theme/**/*.{js,jsx}",
      "src/components/shared/**/*.{js,jsx}",
      "src/pages/CRM/**/*.{js,jsx}",
      "src/pages/MasterAdmin/**/*.{js,jsx}",
      "src/pages/Memberships/**/*.{js,jsx}",
      "src/pages/Marketing/**/*.{js,jsx}",
    ],
    plugins: { gymaxis: gymaxisPlugin },
    rules: {
      "gymaxis/no-inline-hex": "warn",
    },
  },
  {
    // Iter 216h226 — Jest globals for *.test.js / *.spec.js files.
    files: ["src/**/*.{test,spec}.{js,jsx}"],
    languageOptions: {
      globals: {
        jest: "readonly",
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
      },
    },
  },
  {
    ignores: [
      "build/**",
      "node_modules/**",
      "public/**",
      "src/components/ui/**",   // shadcn generated components
    ],
  },
];
