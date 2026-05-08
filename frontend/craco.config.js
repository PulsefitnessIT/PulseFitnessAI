// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Security hardening — add security headers + block sensitive path probes
  // (P0 security-audit remediation: /.env, /.git/config, /backend/.env,
  // /package.json, /admin were returning 200 via the React SPA catch-all).
  devServerConfig.headers = {
    ...(devServerConfig.headers || {}),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    // X-Frame-Options intentionally omitted — CSP `frame-ancestors` handles
    // iframe protection and supports the multi-origin allowlist the Emergent
    // preview panel needs (app.emergent.sh → preview.emergentagent.com).
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": [
      "default-src 'self'",
      "img-src 'self' data: blob: https:",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://api.fontshare.com https://challenges.cloudflare.com https://js.hcaptcha.com",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://challenges.cloudflare.com https://js.hcaptcha.com https://js.stripe.com",
      "font-src 'self' data: https://fonts.gstatic.com https://cdn.fontshare.com",
      "connect-src 'self' https: wss: ws:",
      "frame-src 'self' https://challenges.cloudflare.com https://hcaptcha.com https://js.stripe.com",
      // Allow our own origin + Emergent app-builder domains to embed the app
      // in an iframe (preview panel). All other external origins remain blocked.
      "frame-ancestors 'self' https://app.emergent.sh https://*.emergent.sh https://*.emergentagent.com",
      "base-uri 'self'",
      "form-action 'self'",
      // Allow same-origin + blob: objects so the browser PDF viewer can render
      // inline spec sheets from blob URLs. External object sources still blocked.
      "object-src 'self' blob:",
    ].join("; "),
  };

  // Block known-sensitive path probes (return 404 instead of the SPA shell).
  const BLOCKED_PATH_RE = /^\/(\.env|\.git|package\.json|package-lock\.json|yarn\.lock|backend\/\.env|admin|\.ssh|\.htpasswd|\.htaccess|\.DS_Store|web\.config|\.aws|wp-admin|wp-login|phpinfo|composer\.json)(\/|$)/i;

  // CRA uses the legacy `onBeforeSetupMiddleware` hook, which conflicts with
  // the newer `setupMiddlewares` option (webpack-dev-server rejects both).
  // So we compose over `onBeforeSetupMiddleware` to keep CRA happy.
  const originalOnBefore = devServerConfig.onBeforeSetupMiddleware;
  devServerConfig.onBeforeSetupMiddleware = (devServer) => {
    if (devServer && devServer.app && typeof devServer.app.use === "function") {
      devServer.app.use((req, res, next) => {
        if (BLOCKED_PATH_RE.test(req.url || "")) {
          res.status(404).type("text/plain").send("Not Found");
          return;
        }
        next();
      });
    }
    if (typeof originalOnBefore === "function") {
      originalOnBefore(devServer);
    }
    // Keep health check endpoints working if enabled
    if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
      setupHealthEndpoints(devServer, healthPluginInstance);
    }
  };

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

module.exports = webpackConfig;
