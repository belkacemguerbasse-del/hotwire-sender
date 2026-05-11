"""Génération d'une fiche de coupe en PDF.

Construit un document HTML à partir d'un HotWireProject + estimations,
puis l'exporte en PDF via QTextDocument + QPrinter (zéro dépendance
externe).
"""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from .project import HotWireProject


def _esc(s: str) -> str:
    return html.escape(s or "")


def _fmt_duration(s: float) -> str:
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}h {m:02d}min {sec:02d}s"
    return f"{m}min {sec:02d}s"


def build_report_html(
    project: HotWireProject,
    estimate: dict | None = None,
    notes: str = "",
) -> str:
    """Construit la fiche de coupe au format HTML."""
    p = project
    sections_rows = []
    for i, s in enumerate(p.wing.sections):
        sections_rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td><b>{_esc(s.profile_name)}</b></td>"
            f"<td>{s.span_y_mm:.1f} mm</td>"
            f"<td>{s.chord_mm:.1f} mm</td>"
            f"<td>{s.twist_deg:+.2f}°</td>"
            f"<td>{s.offset_x_mm:+.1f} mm</td>"
            f"<td>{s.offset_y_mm:+.1f} mm</td>"
            f"<td>{s.kerf_mm:+.2f} mm</td>"
            f"</tr>"
        )

    estimate_html = ""
    if estimate:
        estimate_html = f"""
        <h2>Estimations</h2>
        <table class='kv'>
            <tr><th>Durée totale estimée</th><td>{_fmt_duration(estimate['total_time_s'])}</td></tr>
            <tr><th>Longueur totale parcourue</th><td>{estimate['total_length_mm']:.0f} mm</td></tr>
            <tr><th>Longueur fil chaud actif</th><td>{estimate['wire_length_mm']:.0f} mm</td></tr>
            <tr><th>Nombre de mouvements</th><td>{estimate['n_moves']}</td></tr>
        </table>
        """

    adaptive_kerf_html = ""
    if getattr(p.cut_params, "adaptive_kerf", False):
        adaptive_kerf_html = (
            f"<tr><th>Kerf adaptatif</th><td>activé "
            f"(vitesse référence : {p.cut_params.kerf_ref_feed:.0f} mm/min)</td></tr>"
        )

    notes_html = ""
    if notes:
        notes_html = (
            f"<h2>Notes</h2><div class='notes'>{_esc(notes).replace(chr(10), '<br>')}</div>"
        )

    return f"""
<html>
<head>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2933; }}
  h1 {{ color: #1f6feb; font-size: 22pt; margin-bottom: 4pt; }}
  h2 {{ color: #1f6feb; border-bottom: 2px solid #1f6feb;
        padding-bottom: 2pt; margin-top: 18pt; font-size: 14pt; }}
  .meta {{ color: #637381; font-size: 9pt; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 6pt; }}
  th, td {{ border: 1px solid #d6dde6; padding: 5pt 8pt; text-align: left; font-size: 10pt; }}
  th {{ background: #f3f5f8; color: #1f2933; font-weight: 600; }}
  table.kv th {{ width: 40%; }}
  table.kv td {{ font-family: Consolas, monospace; }}
  .notes {{ background: #f3f5f8; border-left: 4px solid #1f6feb;
            padding: 8pt 12pt; margin-top: 6pt; font-size: 10pt; }}
  .footer {{ color: #9aa3ad; font-size: 8pt; text-align: center;
             margin-top: 30pt; padding-top: 6pt; border-top: 1px solid #d6dde6; }}
</style>
</head>
<body>
<h1>🔥 Fiche de coupe — HotWire Sender</h1>
<div class='meta'>Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")}</div>

<h2>Géométrie machine</h2>
<table class='kv'>
    <tr><th>Distance entre tours (L_fil)</th><td>{p.geometry.wire_span:.1f} mm</td></tr>
    <tr><th>Tour gauche → face emplanture</th><td>{p.geometry.block_root_x:.1f} mm</td></tr>
    <tr><th>Tour gauche → face saumon</th><td>{p.geometry.block_tip_x:.1f} mm</td></tr>
    <tr><th>Largeur du bloc</th><td>{p.geometry.block_tip_x - p.geometry.block_root_x:.1f} mm</td></tr>
</table>

<h2>Aile : {p.wing.n_sections} sections / {p.wing.n_panels} panneau(x)</h2>
<table>
    <tr>
        <th>#</th><th>Profil</th><th>Y envergure</th><th>Corde</th>
        <th>Twist</th><th>Offset X</th><th>Offset Y</th><th>Kerf</th>
    </tr>
    {''.join(sections_rows)}
</table>
<p class='meta'>Envergure totale : <b>{p.wing.total_span_mm:.1f} mm</b></p>

<h2>Paramètres de coupe</h2>
<table class='kv'>
    <tr><th>Avance de coupe (F)</th><td>{p.cut_params.feed:.0f} mm/min</td></tr>
    <tr><th>Puissance fil chaud (S)</th><td>{p.cut_params.hot_wire_s}</td></tr>
    <tr><th>Lead-in</th><td>{p.cut_params.leadin_mm:.1f} mm</td></tr>
    <tr><th>Lead-out</th><td>{p.cut_params.leadout_mm:.1f} mm</td></tr>
    <tr><th>Points par profil</th><td>{p.cut_params.n_resample}</td></tr>
    <tr><th>Y de sécurité</th><td>{p.cut_params.safe_y:.1f} mm</td></tr>
    <tr><th>Mode de génération</th><td>{p.cut_params.mode}</td></tr>
    {adaptive_kerf_html}
</table>

{estimate_html}

{notes_html}

<div class='footer'>
HotWire Sender — Fiche générée automatiquement.
Conserver avec le fichier .gcode et la mousse pour traçabilité.
</div>
</body>
</html>
"""


def export_pdf(
    project: HotWireProject,
    output_path: str,
    estimate: dict | None = None,
    notes: str = "",
) -> None:
    """Génère le PDF à `output_path`."""
    html_content = build_report_html(project, estimate=estimate, notes=notes)

    doc = QTextDocument()
    doc.setHtml(html_content)

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(output_path)
    layout = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Portrait,
        QMarginsF(15, 15, 15, 15),
        QPageLayout.Millimeter,
    )
    printer.setPageLayout(layout)

    doc.print_(printer)
