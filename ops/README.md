# GymAxis Ops — Edge Security Deployment

Terraform module + scripts for deploying the Cloudflare WAF + rate-limits documented in `/app/memory/SECURITY_OPS.md`.

## Prerequisites

1. Terraform ≥ 1.5
2. A Cloudflare account with `gymaxis.ai` zone added (orange-cloud proxied).
3. API token with these scopes:
   - `Zone.Zone Settings:Edit`
   - `Zone.WAF:Edit`
   - `Account.Bot Management:Edit` (optional)

## Deploy

```bash
cd /app/ops
cp terraform.tfvars.example terraform.tfvars
# Fill in cloudflare_api_token, zone_id, office_ip_set
terraform init
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

## Verify

After `apply`, confirm in the Cloudflare dashboard:

- **Security → WAF → Managed Rules** shows OWASP CRS + Cloudflare Managed Ruleset both **On**
- **Security → WAF → Custom Rules** shows 3 GymAxis rules (master-admin IP block, login threat-score challenge, SQLi/XSS auth block)
- **Security → WAF → Rate Limiting Rules** shows 2 limits (/api/support/ask 10/min, /api/auth/* POST 20/min)
- **Security → Bots** shows Bot Fight Mode enabled

## Rolling back

```bash
terraform destroy
```

Will remove all Terraform-managed rules but leave any manual Cloudflare rules untouched.

## What this does NOT cover

- **DNS** — manage separately in Cloudflare (not in Terraform to avoid accidental propagation of bad records).
- **Cache rules** — product / performance concern, handled by the caching team.
- **Origin cert pinning** — enable via Cloudflare dashboard once infra is ready.
