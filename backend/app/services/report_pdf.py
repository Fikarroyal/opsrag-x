"""PDF export of an investigation report (ReportLab)."""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

H = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=H["Title"], fontSize=16, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=H["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=3, textColor=colors.HexColor("#1e3a5f"))
BODY = ParagraphStyle("b", parent=H["BodyText"], fontSize=8.8, leading=11.2)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=7.6, leading=9.4)


def _p(text: Any, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    data = [[_p(c, SMALL) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5ccd6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf4")))
    t.setStyle(TableStyle(style))
    return t


def build_pdf(report: dict[str, Any], meta: dict[str, Any], events: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Investigation {meta.get('ticket_number', '')}",
        author="OpsRAG-X",
    )
    W = A4[0] - 3.2 * cm
    inc, cls = report["incident"], report["classification"]
    s: list[Any] = [_p("OpsRAG-X - Laporan Investigasi Incident", TITLE), _p(f"{inc['ticket_number']} - {inc['title']}"), Spacer(1, 4)]
    s += [_p("1. Ringkasan Incident", H2), _p(report["incident_summary"])]
    if report.get("ai_narrative"):
        s.append(_p(f"Ringkasan AI (LLM, dibatasi pada fakta di atas): {report['ai_narrative']}", SMALL))
    s.append(_p(f"Deskripsi: {inc['description']}", SMALL))
    s += [
        _p("2. Klasifikasi", H2),
        _table(
            [
                ["Kategori", "Sekunder", "Severity", "Cakupan", "Layanan", "Metode/Confidence"],
                [
                    cls["category"],
                    cls["secondary_category"] or "-",
                    cls["severity"],
                    cls["affected_scope"],
                    cls["affected_service"] or "-",
                    f"{cls['method']} / {cls['confidence']}",
                ],
            ],
            [W / 6] * 6,
        ),
    ]
    s.append(_p("3. Investigation Timeline", H2))
    s.append(
        _table(
            [["Waktu", "Sumber", "Event", "Relasi"]]
            + [[t["timestamp"].replace("T", " ")[:19], t["source"], t["event"], t.get("relation") or ""] for t in report["timeline"][:28]],
            [3.3 * cm, 3.4 * cm, W - 9.2 * cm, 2.5 * cm],
        )
    )
    s.append(_p("4. Evidence", H2))
    s.append(
        _table(
            [["Key", "Sumber", "Jenis", "Peran", "Isi", "Rel."]]
            + [
                [e["key"], e["source_type"], e["kind"], e["role"], e["content"][:230], e["relevance_score"]]
                for e in report["evidence"][:30]
            ],
            [1.1 * cm, 2.3 * cm, 1.8 * cm, 2.0 * cm, W - 8.4 * cm, 1.2 * cm],
        )
    )
    s += [
        _p("5. Hipotesis Root Cause & 6. Confidence", H2),
        _p("Confidence = evidence confidence score (bukan probabilitas statistik).", SMALL),
    ]
    for h in report["root_cause_hypotheses"][:4]:
        s.append(_p(f"{h['id']} [{h['status']}] {h['description']} - confidence {h['confidence']:.0%} (score {h['score']})", BODY))
        s.append(_p("Komponen: " + ", ".join(f"{k}={v}" for k, v in h["components"].items()), SMALL))
        s.append(_p("Pendukung: " + (" | ".join(f"[{x['key']}] {x['text'][:130]}" for x in h["supporting_evidence"][:4]) or "-"), SMALL))
        s.append(
            _p("Kontradiksi: " + (" | ".join(f"[{x['key']}] {x['text'][:130]}" for x in h["contradicting_evidence"][:3]) or "-"), SMALL)
        )
        s.append(
            _p("Mengapa: " + h["explainability"]["why"][:380] + " Diagnostik berikutnya: " + h["explainability"]["next_diagnostic"], SMALL)
        )
    s.append(_p("7. Referensi SOP", H2))
    s.append(
        _table(
            [["SOP", "Versi", "Berlaku", "Judul", "Relevansi"]]
            + [[r["sop_code"], r["version"], r["effective_date"], r["title"], r["relevance"]] for r in report["sop_reference"]],
            [2 * cm, 1.4 * cm, 2.4 * cm, W - 8.2 * cm, 2.4 * cm],
        )
    )
    s.append(_p("8. Incident Historis (supporting evidence only)", H2))
    s.append(
        _table(
            [["ID", "Tanggal", "Unit", "Penyebab tercatat", "Penyelesaian", "Kemiripan"]]
            + [
                [h["incident_key"], h["timestamp"][:10], h["unit"], h["root_cause"][:70], (h["resolution"] or "")[:70], h["similarity"]]
                for h in report["historical_incidents"][:6]
            ],
            (
                [1.9 * cm, 2 * cm, 1.8 * cm, (W - 10.4) / 2 * 1 + 2.4 * cm, (W - 10.4) / 2 * 1 + 2.4 * cm, 1.6 * cm]
                if False
                else [1.9 * cm, 2 * cm, 1.8 * cm, 4.6 * cm, 5.0 * cm, 1.6 * cm]
            ),
        )
    )
    s.append(_p("9. Diagnostik MCP (read-only)", H2))
    s.append(
        _table(
            [["Tool", "Tujuan", "Status", "ms", "Ringkasan hasil"]]
            + [
                [t["tool"], t["purpose"][:70], t["status"], t["execution_ms"], (t["summary"] or t["error"] or "")[:120]]
                for t in report["tools_executed"]
            ],
            [3 * cm, 4.2 * cm, 1.6 * cm, 1.2 * cm, W - 10 * cm],
        )
    )
    s.append(_p("10. Rekomendasi & 11. Langkah Verifikasi", H2))
    for a in report["recommended_actions"]:
        s.append(
            _p(
                f"{a['order']}. {a['text']} [evidence: {', '.join(a['evidence_refs'])}]"
                + (f" [{a['sop_reference']}]" if a.get("sop_reference") else ""),
                BODY,
            )
        )
    s.append(_p("Verifikasi: " + "; ".join(report["verification_steps"]), SMALL))
    s.append(_p("12. Keterbatasan", H2))
    for lim in report["limitations"]:
        s.append(_p(f"- {lim}", SMALL))
    s.append(_p("13. Audit", H2))
    a = report.get("audit", {})
    s.append(
        _table(
            [
                ["Field", "Nilai"],
                ["Investigation ID", a.get("investigation_id")],
                ["Parent (replay)", a.get("parent_investigation_id") or "-"],
                ["Request ID", a.get("request_id") or "-"],
                ["Mode AI", report["ai_mode"]],
                ["Model", report["model_used"]],
                ["Embedding", a.get("embedding")],
                ["Disimpan", a.get("stored_at")],
                ["Jumlah event audit", len(events)],
            ],
            [4 * cm, W - 4 * cm],
        )
    )
    doc.build(s)
    return buf.getvalue()
