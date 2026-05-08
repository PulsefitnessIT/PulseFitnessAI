# Cloudflare WAF rules for GymAxis / Pulse Fitness API (P3+, Feb 2026).
#
# Usage:
#   1. cp terraform.tfvars.example terraform.tfvars
#   2. Fill in your Cloudflare API token + Zone ID + Account ID.
#   3. terraform init && terraform plan && terraform apply
#
# Applies:
#   - OWASP Core Rule Set (paranoia level 2, action: block)
#   - Cloudflare Managed Ruleset (action: block)
#   - Account-takeover-prevention via threat score on /api/auth/login
#   - Master-admin path IP allowlist (defence-in-depth over app-level allowlist)
#   - LLM-abuse rate limiter on /api/support/ask
#   - Bot Fight Mode
#
# After apply, every incoming request is scored + filtered *before* it reaches
# our FastAPI backend. The app-level controls stay as a second line of defence.

terraform {
  required_version = ">= 1.5"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.30"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ─── OWASP Core Rule Set (paranoia 2, block) ─────────────────────
resource "cloudflare_ruleset" "owasp_managed" {
  zone_id = var.zone_id
  name    = "OWASP Core Rule Set"
  kind    = "zone"
  phase   = "http_request_firewall_managed"

  rules {
    action = "execute"
    action_parameters {
      id = "4814384a9e5d4991b9815dcfc25d2f1f" # Cloudflare OWASP Ruleset UUID
      overrides {
        action = "block"
        rules {
          id      = "7b6de7c2c59b457ea8d0c4b0f3c66527" # sensitivity
          enabled = true
          score_threshold = 25  # paranoia level ~2
        }
      }
    }
    expression  = "true"
    description = "OWASP-managed: block all paranoia-2 hits"
    enabled     = true
  }
}

# ─── Cloudflare Managed Ruleset (block) ──────────────────────────
resource "cloudflare_ruleset" "cf_managed" {
  zone_id = var.zone_id
  name    = "Cloudflare Managed Ruleset"
  kind    = "zone"
  phase   = "http_request_firewall_managed"

  rules {
    action = "execute"
    action_parameters {
      id = "efb7b8c949ac4650a09736fc376e9aee" # Cloudflare Managed Ruleset UUID
    }
    expression  = "true"
    description = "Cloudflare-managed rules block known-bad patterns"
    enabled     = true
  }
}

# ─── Custom rules ────────────────────────────────────────────────
resource "cloudflare_ruleset" "gymaxis_custom" {
  zone_id = var.zone_id
  name    = "GymAxis custom WAF"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  # Block master-admin access from outside office IPs (defence-in-depth).
  rules {
    action      = "block"
    expression  = "(http.request.uri.path contains \"/api/master-admin/\") and not (ip.src in ${var.office_ip_set})"
    description = "Block master-admin from non-office IPs"
    enabled     = true
  }

  # Challenge login attempts with high threat score.
  rules {
    action      = "managed_challenge"
    expression  = "(http.request.uri.path eq \"/api/auth/login\") and (cf.threat_score gt 30)"
    description = "Challenge suspicious /auth/login requests"
    enabled     = true
  }

  # Block SQLi/XSS patterns on JSON-posted auth bodies (belt-and-braces).
  rules {
    action      = "block"
    expression  = "(http.request.uri.path starts_with \"/api/auth/\") and (http.request.body.raw contains \"union select\" or http.request.body.raw contains \"<script\")"
    description = "Block SQLi/XSS patterns on auth endpoints"
    enabled     = true
  }
}

# ─── Rate limiting rules ──────────────────────────────────────────
resource "cloudflare_ruleset" "gymaxis_rate_limits" {
  zone_id = var.zone_id
  name    = "GymAxis rate limits"
  kind    = "zone"
  phase   = "http_ratelimit"

  # LLM abuse protection: 10 /api/support/ask calls / min per IP.
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["ip.src"]
      period              = 60
      requests_per_period = 10
      mitigation_timeout  = 300
    }
    expression  = "http.request.uri.path eq \"/api/support/ask\""
    description = "Throttle /api/support/ask (LLM abuse)"
    enabled     = true
  }

  # Auth endpoint hammering: 20 POSTs / min per IP across all /auth/*.
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["ip.src"]
      period              = 60
      requests_per_period = 20
      mitigation_timeout  = 900
    }
    expression  = "(http.request.uri.path starts_with \"/api/auth/\") and (http.request.method eq \"POST\")"
    description = "Throttle POSTs to /api/auth/* (credential stuffing)"
    enabled     = true
  }
}

# ─── Bot management ───────────────────────────────────────────────
resource "cloudflare_zone_settings_override" "gymaxis" {
  zone_id = var.zone_id
  settings {
    security_level          = "high"
    challenge_ttl           = 1800
    browser_check           = "on"
    always_use_https        = "on"
    min_tls_version         = "1.2"
    opportunistic_encryption = "on"
    automatic_https_rewrites = "on"
  }
}

# ─── Bot Fight Mode (free tier) ──────────────────────────────────
resource "cloudflare_bot_management" "gymaxis" {
  zone_id                    = var.zone_id
  fight_mode                 = true
  using_latest_model         = true
  enable_js                  = true
  auto_update_model          = true
}

# ─── Variables ────────────────────────────────────────────────────
variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Cloudflare API token with Zone.WAF:Edit + Zone.Settings:Edit"
}

variable "zone_id" {
  type        = string
  description = "Cloudflare Zone ID for gymaxis.ai"
}

variable "office_ip_set" {
  type        = string
  default     = "{203.0.113.0/24 198.51.100.5}"
  description = "Space-separated CIDR / IPs wrapped in braces — office + VPN ranges"
}
