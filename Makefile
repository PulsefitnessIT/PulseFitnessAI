# GymAxis · convenience targets
#
# Common tasks the engineering team runs locally / in CI.
# Keep this file lean — actual logic lives in scripts/.

.PHONY: help lint-integrations lint-backend lint-frontend lint smoke

help:
	@echo "GymAxis make targets:"
	@echo "  make lint-integrations   # validate Sicon/Sage field mapping docs"
	@echo "  make lint-backend        # ruff over backend/"
	@echo "  make lint-frontend       # eslint over frontend/src/"
	@echo "  make lint                # all of the above"
	@echo "  make smoke               # quick health curl against $$REACT_APP_BACKEND_URL"

lint-integrations:
	@python3 /app/backend/scripts/check_integration_mapping.py

lint-backend:
	@cd /app/backend && ruff check . || true

lint-frontend:
	@cd /app/frontend && yarn -s eslint src --ext .js,.jsx --max-warnings 0 || true

lint: lint-integrations lint-backend lint-frontend

smoke:
	@URL=$$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d'=' -f2); \
	  curl -fsS "$$URL/api/health" >/dev/null && echo "OK: backend reachable at $$URL/api/health" || echo "FAIL: backend not reachable"
