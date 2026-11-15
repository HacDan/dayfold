# Dayfold: common tasks. Requires uv (Python) and pnpm (Node 20+).
KINDLE ?= kindle
PORT ?= 8422
SERVER ?= http://$(shell hostname -I 2>/dev/null | awk '{print $$1}'):$(PORT)

.PHONY: setup build dev-backend dev-frontend serve generate test test-koreader lint install kindle-install kindle-koreader kindle-library kindle-agent kindle-screensaver

setup:
	cd backend && uv sync
	cd frontend && pnpm install

build:
	cd frontend && pnpm build

serve: build
	cd backend && uv run dayfold serve

dev-backend:
	cd backend && DAYFOLD_PORT=$(PORT) uv run uvicorn dayfold.app:app --reload --port $(PORT)

dev-frontend:
	cd frontend && DAYFOLD_BACKEND=http://localhost:$(PORT) pnpm dev

generate:
	cd backend && uv run dayfold generate

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uvx ruff check dayfold tests

# Install as a systemd user service (see deploy/dayfold.service).
install: setup build
	mkdir -p $(HOME)/.config/systemd/user $(HOME)/.config/dayfold
	test -f $(HOME)/.config/dayfold/env || cp deploy/env.example $(HOME)/.config/dayfold/env
	sed "s#@REPO@#$(CURDIR)#g" deploy/dayfold.service > $(HOME)/.config/systemd/user/dayfold.service
	systemctl --user daemon-reload
	systemctl --user enable --now dayfold.service
	@echo "Dayfold em http://localhost:$(PORT) (logs: journalctl --user -u dayfold -f)"

# Kindle over SSH (jailbroken, see docs/KINDLE.md).
kindle-koreader:
	KINDLE=$(KINDLE) ./kindle/install-koreader.sh

kindle-install:
	KINDLE=$(KINDLE) SERVER=$(SERVER) ./kindle/install-plugin.sh

# KOReader plugin: catalogue, reader hook and the download/rename handling (see koreader/tests).
# LuaJIT is required: skipping these tests silently would hide a broken catalogue.
test-koreader:
	@command -v luajit >/dev/null 2>&1 || { echo "luajit não encontrado: instale o LuaJIT (brew install luajit, apt install luajit)" >&2; exit 1; }
	luajit koreader/tests/test_l10n.lua
	luajit koreader/tests/test_reader_hook.lua
	luajit koreader/tests/test_sync_games.lua

kindle-library:
	KINDLE=$(KINDLE) ./kindle/install-kompanion.sh

kindle-agent:
	KINDLE=$(KINDLE) ./kindle/install-agent.sh

kindle-screensaver: kindle-agent
