.PHONY: install download process build-kb audit dashboard pipeline clean

YEARS ?= 1998-2025
PYTHON = python
STREAMLIT = streamlit

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

lint:
	ruff check src/ scripts/
	ruff format --check src/ scripts/

.PHONY: help
help:
	@echo "CFP Audit Intelligence – Make targets:"
	@echo "  install        Instalar dependencias"
	@echo "  download       Descargar todas las actas del CFP"
	@echo "  process        Extraer texto y parsear resoluciones"
	@echo "  build-kb       Construir knowledge base vectorial"
	@echo "  audit          Correr análisis IA (requiere ANTHROPIC_API_KEY)"
	@echo "  audit-sample   Auditar muestra de 50 documentos"
	@echo "  pipeline       Pipeline completo end-to-end"
	@echo "  dashboard      Lanzar dashboard Streamlit"
	@echo "  stats          Ver estadísticas del catálogo"
	@echo "  clean-kb       Eliminar knowledge base"
	@echo "  clean-all      Eliminar todos los datos generados"
	@echo ""
	@echo "Variables:"
	@echo "  YEARS=1998-2025  Rango de años para descarga (default: 1998-2025)"
