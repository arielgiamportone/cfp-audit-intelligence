"""
Generador de reportes PDF ejecutivos para el CFP Audit Intelligence.

Produce un informe técnico con portada, resumen ejecutivo, hallazgos
de auditoría, comparaciones CFP-INIDEP, alertas activas y gráficos.
"""
import io
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import KeepTogether


# ── Paleta de colores ──────────────────────────────────────────────────────────

COLOR_PRIMARY = colors.HexColor("#1565C0")   # azul oscuro
COLOR_ACCENT = colors.HexColor("#E65100")    # naranja
COLOR_DANGER = colors.HexColor("#C62828")    # rojo
COLOR_WARNING = colors.HexColor("#F57F17")   # ámbar
COLOR_SUCCESS = colors.HexColor("#2E7D32")   # verde
COLOR_LIGHT = colors.HexColor("#E3F2FD")     # azul muy claro
COLOR_GRAY = colors.HexColor("#757575")      # gris
COLOR_DARK = colors.HexColor("#212121")      # casi negro

ALERTA_COLORS = {
    "verde": COLOR_SUCCESS,
    "amarillo": COLOR_WARNING,
    "rojo": COLOR_DANGER,
    "critico": COLOR_DANGER,
    "sin_datos": COLOR_GRAY,
    "critical": COLOR_DANGER,
    "warning": COLOR_WARNING,
    "info": COLOR_PRIMARY,
}

W, H = A4


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=24, textColor=COLOR_PRIMARY,
            spaceAfter=6, alignment=TA_CENTER, leading=28,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=13, textColor=COLOR_GRAY,
            spaceAfter=4, alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontSize=16, textColor=COLOR_PRIMARY,
            spaceBefore=16, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=12, textColor=COLOR_DARK,
            spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10, leading=14, alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontSize=8, textColor=COLOR_GRAY,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "alert_critical": ParagraphStyle(
            "AlertCritical",
            parent=base["Normal"],
            fontSize=9, textColor=COLOR_DANGER,
            backColor=colors.HexColor("#FFEBEE"),
            leftIndent=8, rightIndent=8, spaceAfter=4,
        ),
        "alert_warning": ParagraphStyle(
            "AlertWarning",
            parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#E65100"),
            backColor=colors.HexColor("#FFF3E0"),
            leftIndent=8, rightIndent=8, spaceAfter=4,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            parent=base["Normal"],
            fontSize=22, textColor=COLOR_PRIMARY,
            alignment=TA_CENTER, leading=26,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["Normal"],
            fontSize=8, textColor=COLOR_GRAY,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=7, textColor=COLOR_GRAY,
            alignment=TA_CENTER,
        ),
    }
    return styles


class CFPReportGenerator:
    """Genera reportes PDF ejecutivos del sistema CFP Audit Intelligence."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)
        self.styles = _build_styles()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _safe_query(self, query: str, params=()) -> list:
        if not self.db_path.exists():
            return []
        try:
            with self._conn() as conn:
                return conn.execute(query, params).fetchall()
        except sqlite3.OperationalError as e:
            logger.debug(f"Query omitida: {e}")
            return []

    def _safe_scalar(self, query: str, params=(), default=0):
        rows = self._safe_query(query, params)
        return rows[0][0] if rows else default

    # ── Recolección de datos ───────────────────────────────────────────────────

    def _get_stats(self) -> dict:
        return {
            "total_actas": self._safe_scalar("SELECT COUNT(*) FROM actas"),
            "actas_descargadas": self._safe_scalar(
                "SELECT COUNT(*) FROM actas WHERE download_status='downloaded'"
            ),
            "actas_procesadas": self._safe_scalar(
                "SELECT COUNT(*) FROM actas WHERE text_extracted=1"
            ),
            "total_resoluciones": self._safe_scalar("SELECT COUNT(*) FROM resoluciones"),
            "total_entidades": self._safe_scalar("SELECT COUNT(*) FROM entidades"),
            "total_menciones": self._safe_scalar("SELECT COUNT(*) FROM menciones"),
            "años_min": self._safe_scalar("SELECT MIN(year) FROM actas WHERE year IS NOT NULL"),
            "años_max": self._safe_scalar("SELECT MAX(year) FROM actas WHERE year IS NOT NULL"),
            "n_empresas": self._safe_scalar(
                "SELECT COUNT(*) FROM entidades WHERE tipo='empresa'"
            ),
            "n_especies": self._safe_scalar(
                "SELECT COUNT(*) FROM entidades WHERE tipo='especie'"
            ),
        }

    def _get_alertas_criticas(self) -> list:
        return self._safe_query(
            """SELECT tipo, especie, zona, year, valor_detectado, umbral, mensaje, severidad
               FROM alertas_historial
               WHERE resuelta = 0 AND severidad IN ('critical', 'warning')
               ORDER BY CASE severidad WHEN 'critical' THEN 0 ELSE 1 END, year DESC
               LIMIT 20"""
        )

    def _get_comparaciones(self) -> list:
        return self._safe_query(
            """SELECT especie, zona, year, cba_inidep_tn, cmp_cfp_tn,
                      ratio_sobreasignacion, nivel_alerta
               FROM comparacion_cfp_inidep
               WHERE cba_inidep_tn IS NOT NULL AND cmp_cfp_tn IS NOT NULL
               ORDER BY ratio_sobreasignacion DESC
               LIMIT 15"""
        )

    def _get_top_empresas(self) -> list:
        return self._safe_query(
            """SELECT e.nombre, COUNT(m.id) as n_menciones, e.tipo
               FROM entidades e
               JOIN menciones m ON e.id = m.entidad_id
               WHERE e.tipo = 'empresa'
               GROUP BY e.id
               ORDER BY n_menciones DESC
               LIMIT 10"""
        )

    def _get_top_especies(self) -> list:
        return self._safe_query(
            """SELECT e.nombre, COUNT(m.id) as n_menciones
               FROM entidades e
               JOIN menciones m ON e.id = m.entidad_id
               WHERE e.tipo = 'especie'
               GROUP BY e.id
               ORDER BY n_menciones DESC
               LIMIT 10"""
        )

    def _get_resol_por_año(self) -> list:
        return self._safe_query(
            """SELECT a.year, COUNT(r.id) as n_resoluciones
               FROM resoluciones r
               JOIN actas a ON r.acta_id = a.id
               WHERE a.year IS NOT NULL
               GROUP BY a.year
               ORDER BY a.year"""
        )

    # ── Componentes visuales ───────────────────────────────────────────────────

    def _metric_table(self, metrics: list[tuple[str, str]]) -> Table:
        """Tabla de métricas destacadas (valor + etiqueta)."""
        s = self.styles
        cells = []
        for val, label in metrics:
            cells.append([
                Paragraph(str(val), s["metric_value"]),
                Paragraph(label, s["metric_label"]),
            ])

        # Distribuir en filas de 4
        rows = []
        for i in range(0, len(cells), 4):
            chunk = cells[i:i+4]
            while len(chunk) < 4:
                chunk.append(["", ""])
            rows.append([c[0] for c in chunk])
            rows.append([c[1] for c in chunk])

        col_w = (W - 4*cm) / 4
        t = Table(rows, colWidths=[col_w] * 4)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [COLOR_LIGHT, colors.white]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBDEFB")),
            ("ROUNDEDCORNERS", [4]),
        ]))
        return t

    def _comparaciones_table(self, rows: list) -> Table:
        s = self.styles
        header = ["Especie", "Zona", "Año", "CBA (tn)", "CMP (tn)", "Ratio", "Alerta"]
        data = [header]
        for r in rows:
            ratio = r["ratio_sobreasignacion"] or 0
            nivel = r["nivel_alerta"] or "sin_datos"
            color_alerta = ALERTA_COLORS.get(nivel, COLOR_GRAY)
            data.append([
                r["especie"] or "—",
                r["zona"] or "—",
                str(r["year"] or "—"),
                f"{r['cba_inidep_tn']:,.0f}" if r["cba_inidep_tn"] else "—",
                f"{r['cmp_cfp_tn']:,.0f}" if r["cmp_cfp_tn"] else "—",
                f"{ratio:.2f}x",
                nivel.upper(),
            ])

        col_widths = [4.5*cm, 2.5*cm, 1.5*cm, 2.2*cm, 2.2*cm, 1.8*cm, 2.3*cm]
        t = Table(data, colWidths=col_widths, repeatRows=1)

        style = [
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BDBDBD")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        # Colorear celda alerta
        for i, r in enumerate(rows, start=1):
            nivel = r["nivel_alerta"] or "sin_datos"
            c = ALERTA_COLORS.get(nivel, COLOR_GRAY)
            style.append(("TEXTCOLOR", (6, i), (6, i), c))
            style.append(("FONTNAME", (6, i), (6, i), "Helvetica-Bold"))

        t.setStyle(TableStyle(style))
        return t

    def _empresas_table(self, rows: list) -> Table:
        header = ["Empresa", "Co-menciones en resoluciones"]
        data = [header] + [[r["nombre"], str(r["n_menciones"])] for r in rows]
        t = Table(data, colWidths=[11*cm, 6*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBE9E7")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BDBDBD")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    # ── Construcción del documento ─────────────────────────────────────────────

    def generate(
        self,
        output_path: Optional[Path | str] = None,
        title: str = "Auditoría CFP — Informe Ejecutivo",
        periodo: str = "1998–2025",
        author: str = "CFP Audit Intelligence",
    ) -> bytes:
        """
        Genera el reporte PDF y lo retorna como bytes.
        Si se provee output_path, también lo guarda en disco.
        """
        buf = io.BytesIO()
        s = self.styles

        doc = BaseDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2.5*cm,
            title=title,
            author=author,
        )

        # ── Frames y page templates ────────────────────────────────────────────
        content_frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height,
            id="main",
        )
        cover_frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height,
            id="cover",
        )

        def _footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(COLOR_GRAY)
            now = datetime.now().strftime("%Y-%m-%d")
            canvas.drawCentredString(
                W / 2, 1.2*cm,
                f"CFP Audit Intelligence | {title} | Generado: {now} | Pág. {doc.page}",
            )
            canvas.restoreState()

        doc.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame]),
            PageTemplate(id="main", frames=[content_frame], onPage=_footer),
        ])

        story = []

        # ── 1. PORTADA ─────────────────────────────────────────────────────────
        story.append(Spacer(1, 3*cm))
        story.append(HRFlowable(width="100%", thickness=3, color=COLOR_PRIMARY))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("CONSEJO FEDERAL PESQUERO", ParagraphStyle(
            "OrgName", fontSize=11, textColor=COLOR_GRAY,
            alignment=TA_CENTER, spaceAfter=4,
        )))
        story.append(Paragraph(title, s["title"]))
        story.append(Paragraph(f"Período analizado: {periodo}", s["subtitle"]))
        story.append(Spacer(1, 0.3*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
        story.append(Spacer(1, 2*cm))

        now_str = datetime.now().strftime("%d de %B de %Y")
        cover_meta = [
            ["Fecha de generación:", now_str],
            ["Sistema:", "CFP Audit Intelligence v0.3"],
            ["Base legal:", "Ley 24.922 — Régimen Federal de Pesca"],
            ["Fuentes:", "Actas CFP + Evaluaciones INIDEP (Mar Abierto)"],
            ["Clasificación:", "Información pública — libre distribución"],
        ]
        meta_table = Table(cover_meta, colWidths=[5*cm, 11*cm])
        meta_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), COLOR_PRIMARY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, COLOR_GRAY),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 2*cm))

        disclaimer = (
            "<b>Aviso:</b> Este informe es generado automáticamente a partir de documentos "
            "públicos del CFP. El análisis es descriptivo y no constituye acusación legal. "
            "Los datos son trazables y reproducibles desde el repositorio público del proyecto."
        )
        story.append(Paragraph(disclaimer, ParagraphStyle(
            "Disclaimer", fontSize=8, textColor=COLOR_GRAY,
            backColor=colors.HexColor("#FFFDE7"),
            leftIndent=10, rightIndent=10,
            borderPad=8, alignment=TA_JUSTIFY,
        )))

        story.append(NextPageTemplate("main"))
        story.append(PageBreak())

        # ── 2. RESUMEN EJECUTIVO ───────────────────────────────────────────────
        stats = self._get_stats()
        story.append(Paragraph("1. Resumen Ejecutivo", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
        story.append(Spacer(1, 0.3*cm))

        resumen_text = (
            f"El sistema CFP Audit Intelligence ha procesado <b>{stats['total_actas']}</b> actas "
            f"públicas del Consejo Federal Pesquero correspondientes al período <b>{stats['años_min']}–"
            f"{stats['años_max']}</b>. Se extrajeron <b>{stats['total_resoluciones']:,}</b> resoluciones "
            f"y decisiones, identificando <b>{stats['n_especies']}</b> especies pesqueras y "
            f"<b>{stats['n_empresas']}</b> empresas del sector en <b>{stats['total_menciones']:,}</b> menciones. "
            "El análisis compara las cuotas máximas de captura (CMP) aprobadas por el CFP con las "
            "Capturas Biológicamente Aceptables (CBA) recomendadas por el INIDEP, conforme "
            "lo establece el Art. 9 de la Ley 24.922."
        )
        story.append(Paragraph(resumen_text, s["body"]))
        story.append(Spacer(1, 0.4*cm))

        metrics = [
            (f"{stats['total_actas']:,}", "Actas CFP\nanalizadas"),
            (f"{stats['total_resoluciones']:,}", "Resoluciones\nextraídas"),
            (f"{stats['n_especies']}", "Especies\nmonitoreadas"),
            (f"{stats['n_empresas']}", "Empresas\nidentificadas"),
        ]
        story.append(self._metric_table(metrics))
        story.append(Spacer(1, 0.5*cm))

        # ── 3. ALERTAS ACTIVAS ─────────────────────────────────────────────────
        alertas = self._get_alertas_criticas()
        story.append(Paragraph("2. Alertas de Sostenibilidad Activas", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
        story.append(Spacer(1, 0.3*cm))

        if not alertas:
            story.append(Paragraph(
                "No se detectaron alertas abiertas con los datos actuales. "
                "Ejecutar 'Evaluar ahora' en el dashboard o POST /alertas/evaluar para actualizar.",
                s["body"]
            ))
        else:
            criticas = [a for a in alertas if a["severidad"] in ("critical", "critico")]
            warnings = [a for a in alertas if a["severidad"] == "warning"]

            story.append(Paragraph(
                f"Se detectaron <b>{len(criticas)} alertas críticas</b> y "
                f"<b>{len(warnings)} advertencias</b> sobre la sostenibilidad pesquera:",
                s["body"]
            ))
            story.append(Spacer(1, 0.3*cm))

            for alerta in alertas[:15]:
                sev = alerta["severidad"]
                icon = "🔴" if sev in ("critical", "critico") else "⚠️"
                style_key = "alert_critical" if sev in ("critical", "critico") else "alert_warning"
                story.append(KeepTogether([
                    Paragraph(
                        f"<b>{icon} {alerta['tipo'].replace('_', ' ').upper()}</b>"
                        + (f" | {alerta['especie']}" if alerta["especie"] else "")
                        + (f" | {alerta['year']}" if alerta["year"] else ""),
                        s[style_key]
                    ),
                    Paragraph(alerta["mensaje"], s["body"]),
                ]))

        story.append(PageBreak())

        # ── 4. COMPARACIONES CFP vs. INIDEP ───────────────────────────────────
        comparaciones = self._get_comparaciones()
        story.append(Paragraph("3. Comparación CMP Aprobada vs. CBA Recomendada (INIDEP)", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
        story.append(Spacer(1, 0.3*cm))

        story.append(Paragraph(
            "La Ley 24.922 (Art. 9) establece que el CFP debe fijar las CMP en base a las "
            "evaluaciones científicas del INIDEP. La tabla a continuación muestra los casos "
            "donde la cuota aprobada supera la CBA recomendada, ordenados por ratio de "
            "sobreasignación (mayor a menor).",
            s["body"]
        ))
        story.append(Spacer(1, 0.3*cm))

        if comparaciones:
            story.append(self._comparaciones_table(comparaciones))
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(
                "Leyenda: VERDE = ≤100% CBA | AMARILLO = 101–115% | ROJO = 116–130% | CRÍTICO = >130%",
                s["caption"]
            ))
        else:
            story.append(Paragraph(
                "No hay datos de comparación disponibles. Ejecutar el comparador INIDEP para "
                "cargar evaluaciones y cuotas CFP.",
                s["body"]
            ))

        story.append(Spacer(1, 0.5*cm))

        # ── 5. ACTORES: EMPRESAS Y ESPECIES ───────────────────────────────────
        story.append(Paragraph("4. Principales Actores del Sector", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
        story.append(Spacer(1, 0.3*cm))

        top_empresas = self._get_top_empresas()
        top_especies = self._get_top_especies()

        col1_content = []
        col2_content = []

        if top_empresas:
            col1_content.append(Paragraph("Empresas más mencionadas", s["h2"]))
            col1_content.append(self._empresas_table(top_empresas))

        if top_especies:
            col2_content.append(Paragraph("Especies más mencionadas", s["h2"]))
            esp_data = [["Especie", "Menciones"]] + [
                [r["nombre"], str(r["n_menciones"])] for r in top_especies
            ]
            esp_table = Table(esp_data, colWidths=[7*cm, 3*cm])
            esp_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BDBDBD")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            col2_content.append(esp_table)

        if col1_content or col2_content:
            two_col = Table(
                [[col1_content or [""], col2_content or [""]]],
                colWidths=[doc.width / 2 - 0.5*cm, doc.width / 2 - 0.5*cm],
            )
            two_col.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(two_col)

        story.append(PageBreak())

        # ── 6. METODOLOGÍA ─────────────────────────────────────────────────────
        story.append(Paragraph("5. Metodología y Fuentes", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
        story.append(Spacer(1, 0.3*cm))

        metodologia = [
            ("<b>Fuente de actas CFP:</b>", "Portal oficial CFP (cfp.gob.ar). Descarga automática "
             "de PDFs con rate limiting y retry (tenacity). Extracción de texto en cascada: "
             "pdfplumber → PyMuPDF → OCR Tesseract para documentos escaneados."),
            ("<b>Fuente INIDEP:</b>", "Repositorio Mar Abierto (marabierto.inidep.edu.ar) vía "
             "DSpace 7 REST API. Evaluaciones de stock (ITO) con CBA por especie y año."),
            ("<b>NER pesquero:</b>", "EntityRuler spaCy con 461+ patrones de dominio para detectar "
             "ESPECIE_PESCA, EMPRESA_PESCA, ZONA_PESCA, CUOTA_PESCA, NORMATIVA_CFP, BUQUE_PESCA."),
            ("<b>HHI concentración:</b>", "Índice de Herfindahl-Hirschman calculado como suma de "
             "cuadrados de participaciones de co-menciones × 10.000. HHI > 2.500 indica alta "
             "concentración oligopólica."),
            ("<b>Niveles de alerta:</b>", "VERDE (CMP ≤ 100% CBA) | AMARILLO (101–115%) | "
             "ROJO (116–130%) | CRÍTICO (>130%). Basado en el principio precautorio del Art. 9, "
             "Ley 24.922."),
            ("<b>Reproducibilidad:</b>", "Todo el código es open source. Los datos son "
             "documentos públicos. Las evaluaciones son trazables al ITO del INIDEP correspondiente."),
        ]

        for label, texto in metodologia:
            story.append(KeepTogether([
                Paragraph(label, s["h2"]),
                Paragraph(texto, s["body"]),
                Spacer(1, 0.2*cm),
            ]))

        # ── Build ──────────────────────────────────────────────────────────────
        doc.build(story)
        pdf_bytes = buf.getvalue()

        if output_path:
            Path(output_path).write_bytes(pdf_bytes)
            logger.info(f"Reporte PDF guardado: {output_path} ({len(pdf_bytes):,} bytes)")

        return pdf_bytes


def generate_report(
    db_path: Path | str = "data/processed/catalog.db",
    output_path: Optional[Path | str] = None,
    **kwargs,
) -> bytes:
    """Función de conveniencia para generar el reporte."""
    gen = CFPReportGenerator(db_path=db_path)
    return gen.generate(output_path=output_path, **kwargs)
