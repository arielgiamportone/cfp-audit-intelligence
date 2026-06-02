.PHONY: install download process build-kb audit dashboard pipeline clean \
        docker-build docker-up docker-down docker-logs docker-api docker-shell

YEARS ?= 1998-2025
PYTHON = python
STREAMLIT = streamlit
DOCKER_IMAGE ?= cfp-audit-intelligence:latest

install:
	pip install -r requirements.txt
	python -m spacy download es_core_news_sm

download:
	$(PYTHON) scripts/run_full_pipeline.py --step download --years $(YEARS)

process:
	$(PYTHON) scripts/run_full_pipeline.py --step process

build-kb:
	$(PYTHON) scripts/run_full_pipeline.py --step knowledge_base

audit:
	$(PYTHON) scripts/run_full_pipeline.py --step audit

audit-sample:
	$(PYTHON) scripts/run_full_pipeline.py --step audit --limit 50

pipeline:
	$(PYTHON) scripts/run_full_pipeline.py --step all --years $(YEARS)

dashboard:
	$(STREAMLIT) run src/dashboard/app.py

scraper-legacy:
	$(STREAMLIT) run cfp_scraper.py

clean-kb:
	rm -rf data/knowledge_base/
	@echo "Knowledge base eliminada. Reconstruir con: make build-kb"

clean-processed:
	rm -rf data/processed/text/ data/processed/json/
	@echo "Datos procesados eliminados."

clean-all: clean-kb clean-processed
	rm -rf data/raw/
	@echo "Todos los datos eliminados."

stats:
	$(PYTHON) -c "from src.acquisition.catalog_manager import CatalogManager; \
	              import json; \
	              c = CatalogManager(); \
	              print(json.dumps(c.stats(), indent=2))"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing

update-stats:
	$(PYTHON) scripts/update_test_count.py

check-stats:
	$(PYTHON) scripts/update_test_count.py --check

lint:
	ruff check src/ scripts/
	ruff format --check src/ scripts/

lint-fix:
	ruff check --fix src/ scripts/
	ruff format src/ scripts/

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker build -t $(DOCKER_IMAGE) .

docker-up:
	docker compose up -d
	@echo "API:       http://localhost:8000/docs"
	@echo "Dashboard: http://localhost:8501"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-api:
	docker compose up -d api
	@echo "API disponible en http://localhost:8000/docs"

docker-restart:
	docker compose restart

docker-shell:
	docker compose run --rm api bash

docker-clean:
	docker compose down --volumes --remove-orphans
	docker rmi $(DOCKER_IMAGE) 2>/dev/null || true

.PHONY: help
help:
	@echo "CFP Audit Intelligence – Make targets:"
	@echo ""
	@echo "  Desarrollo local:"
	@echo "  install        Instalar dependencias"
	@echo "  test           Correr tests"
	@echo "  test-cov       Tests con reporte de cobertura"
	@echo "  lint           Verificar estilo de código"
	@echo "  lint-fix       Corregir estilo automáticamente"
	@echo "  update-stats   Sincronizar conteo de tests en la documentación"
	@echo "  check-stats    Verificar drift del conteo de tests (CI)"
	@echo ""
	@echo "  Pipeline de datos:"
	@echo "  download       Descargar todas las actas del CFP"
	@echo "  process        Extraer texto y parsear resoluciones"
	@echo "  build-kb       Construir knowledge base vectorial"
	@echo "  audit          Correr análisis IA (requiere ANTHROPIC_API_KEY)"
	@echo "  audit-sample   Auditar muestra de 50 documentos"
	@echo "  pipeline       Pipeline completo end-to-end"
	@echo ""
	@echo "  Web services:"
	@echo "  dashboard      Lanzar dashboard Streamlit localmente"
	@echo "  stats          Ver estadísticas del catálogo"
	@echo ""
	@echo "  Docker:"
	@echo "  docker-build   Construir imagen Docker"
	@echo "  docker-up      Levantar todos los servicios (API + Dashboard)"
	@echo "  docker-api     Levantar solo la API"
	@echo "  docker-down    Detener todos los servicios"
	@echo "  docker-logs    Ver logs en tiempo real"
	@echo "  docker-shell   Shell interactivo en el contenedor"
	@echo "  docker-clean   Eliminar contenedores e imagen"
	@echo ""
	@echo "  Variables:"
	@echo "  YEARS=1998-2025       Rango de años para descarga"
	@echo "  DOCKER_IMAGE=...      Nombre de la imagen Docker"
