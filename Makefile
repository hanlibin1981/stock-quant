PROJECT_ROOT := /Users/mac/openclaw-projects/stock-quant
PYTHON := ./venv/bin/python

.PHONY: verify build-release healthcheck install-service reload-service stop-service

verify:
	$(PYTHON) -m py_compile src/ui/prod_server.py src/ui/web_app.py src/main.py
	$(PYTHON) -m unittest tests.test_backtest_engine

build-release:
	./scripts/build_release.sh

healthcheck:
	./scripts/healthcheck.sh

install-service:
	./scripts/install_launchd_service.sh

reload-service:
	launchctl unload ~/Library/LaunchAgents/com.stockquant.web.plist >/dev/null 2>&1 || true
	launchctl load ~/Library/LaunchAgents/com.stockquant.web.plist

stop-service:
	launchctl unload ~/Library/LaunchAgents/com.stockquant.web.plist
