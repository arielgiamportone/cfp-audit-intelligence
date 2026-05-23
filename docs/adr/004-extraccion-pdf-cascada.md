# ADR-004: Estrategia de extracción PDF en cascada

**Estado:** Aceptado  
**Fecha:** 2026-05-23  
**Decidido por:** Ariel Giamportone

## Contexto

Las actas del CFP tienen 25+ años de antigüedad. Los PDFs más viejos (1998–2005) son frecuentemente escaneados como imagen, mientras los recientes son texto nativo. Necesitamos una estrategia que maneje ambos casos.

## Estrategia adoptada

```
PDF → pdfplumber → ¿texto ≥ 100 chars? → ✓ OK
                 ↓ NO
              PyMuPDF → ¿texto ≥ 100 chars? → ✓ OK
                 ↓ NO
           Tesseract OCR (300 DPI, lang=spa) → ✓ OK o FAILED
```

## Justificación de cada capa

| Capa | Cuándo actúa | Fortaleza |
|------|-------------|-----------|
| pdfplumber | Mayoría de PDFs modernos | Preserva layout, extrae tablas |
| PyMuPDF (fitz) | PDFs con fuentes embebidas complejas | Rápido, robusto con encoding raros |
| Tesseract | PDFs escaneados (imágenes) | Único método viable para actas pre-2005 |

## Consecuencias

- Procesamiento OCR es ~10x más lento; se limita a PDFs que lo necesiten
- Tesseract requiere instalación del sistema (`tesseract-ocr` + `tesseract-ocr-spa`)
- El método usado se registra en el catálogo para auditoría de calidad
- PDFs de muy baja calidad de escaneo pueden producir texto ilegible (se marca como `failed`)
