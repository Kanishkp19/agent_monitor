import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

def build_pdf():
    output_path = "/Users/kanishk_pandey/Desktop/agentshield/Agent-Shield-/docs/AgentShield_Demo_Video_Script.pdf"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary = colors.HexColor("#0f172a") # Dark slate
    accent = colors.HexColor("#0284c7")  # Tech blue
    highlight = colors.HexColor("#059669") # Green
    dark_text = colors.HexColor("#1e293b")
    dim_text = colors.HexColor("#64748b")
    bg_light = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=accent,
        spaceAfter=12
    )

    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=dim_text
    )

    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=primary,
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=dark_text,
        spaceAfter=6
    )

    spoken_style = ParagraphStyle(
        "Spoken",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#0369a1")
    )

    action_style = ParagraphStyle(
        "Action",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#b45309")
    )

    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white
    )

    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=dark_text
    )

    story = []

    # Title Banner
    story.append(Paragraph("AgentShield Autopilot — 3-Minute Demo Script", title_style))
    story.append(Paragraph("Nebius x NVIDIA Global AI Hackathon · Coding & Agentic Engineering Track", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=accent, spaceBefore=0, spaceAfter=10))

    # Recording Meta Table
    meta_data = [
        [
            Paragraph("<b>Target Length:</b> 2m 45s - 3m 00s (Strict limit: 180s)", meta_style),
            Paragraph("<b>Model:</b> NVIDIA Nemotron 3.5 (30B Lightning)", meta_style)
        ],
        [
            Paragraph("<b>Screen Setup:</b> 1080p (1920x1080) at 100% browser zoom", meta_style),
            Paragraph("<b>Local URL:</b> http://localhost:5173/autopilot", meta_style)
        ],
        [
            Paragraph("<b>Audio:</b> Crisp microphone narration, energetic tone", meta_style),
            Paragraph("<b>Docker:</b> agentshield-autopilot-pytest:2026-10 active", meta_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_light),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Master Timeline Table
    story.append(Paragraph("Timed Scene-by-Scene Director's Cut", h2_style))
    
    headers = [
        Paragraph("Timestamp", table_header),
        Paragraph("On-Screen Visual", table_header),
        Paragraph("Spoken Narration (What to Say)", table_header)
    ]
    
    row1 = [
        Paragraph("<b>0:00 - 0:40</b><br/>(40s)", table_cell),
        Paragraph("<b>App Shell / Title</b><br/>• Show browser at <code>/autopilot</code><br/>• Point to top nav & status indicator: <i>Running Live · NVIDIA Nemotron</i>", table_cell),
        Paragraph("<i>\"Autonomous coding agents are reshaping software development. But giving an LLM direct access to write, patch, and execute code is dangerous—they can hallucinate, tamper with system binaries, escape sandboxes, or leak production secrets.<br/><br/>Meet <b>AgentShield Autopilot</b>: a production runtime governance platform for AI coding agents, powered by <b>NVIDIA Nemotron</b> and containerized test isolation.\"</i>", spoken_style)
    ]

    row2 = [
        Paragraph("<b>0:40 - 1:55</b><br/>(75s)", table_cell),
        Paragraph("<b>Autopilot Live Run</b><br/>• Select <code>buggy-auth</code><br/>• Click <b>Start coding job</b><br/>• Show baseline fail (exit 1)<br/>• Watch Nemotron read files<br/>• Show Gates 1 & 2 approving<br/>• Highlight unified patch diff<br/>• Show container test turn GREEN (exit 0)", table_cell),
        Paragraph("<i>\"Here is Autopilot in action. We select a broken authentication fixture where the session expiry comparison is inverted.<br/><br/>1. Our disposable non-root Docker container executes the baseline test suite with zero network access: six tests fail.<br/>2. <b>NVIDIA Nemotron 3.5</b> begins exploring the repository. Notice every single tool call is intercepted by AgentShield: Gate 1 checks intent, and Gate 2 validates resource permissions and file content hashes.<br/>3. Nemotron pinpoints the bug in <code>app/auth.py</code>, generating an atomic diff fixing <code>now &gt;= expires_at</code> to <code>now &lt; expires_at</code>.<br/>4. The container re-runs pytest in complete isolation: all eight tests pass! exit code zero.\"</i>", spoken_style)
    ]

    row3 = [
        Paragraph("<b>1:55 - 2:30</b><br/>(35s)", table_cell),
        Paragraph("<b>Office Simulation</b><br/>• Click <code>/office</code> in top nav<br/>• Show 5-room Canvas floor<br/>• Show walking employees & halos<br/>• Highlight System Log rail showing <i>Blocked by Gate 2</i>", table_cell),
        Paragraph("<i>\"AgentShield monitors entire multi-agent environments. On the <b>Office Simulation</b>, twenty autonomous agents execute daily developer tasks. Every agent has real-time FSM states, halos, and anomaly scores calculated by an Isolation Forest.<br/><br/>When an agent attempts an unauthorized action—like accessing a production secret or performing directory traversal—AgentShield Gate 2 blocks the action instantly in the system log.\"</i>", spoken_style)
    ]

    row4 = [
        Paragraph("<b>2:30 - 3:00</b><br/>(30s)", table_cell),
        Paragraph("<b>Telemetry & Conclusion</b><br/>• Return to <code>/autopilot</code><br/>• Point to token counter & model latency<br/>• Click <b>Download report</b><br/>• Open the JSON report", table_cell),
        Paragraph("<i>\"Autopilot tracks exact token usage and latency—over 6,000 real input tokens and genuine tool calling with zero mock substitutions. By clicking 'Download report', security teams receive a cryptographically signed JSON audit receipt of the entire job.<br/><br/>AgentShield turns autonomous coding into a governed, verifiable, and enterprise-grade reality. Built with NVIDIA Nemotron on open infrastructure. Thank you!\"</i>", spoken_style)
    ]

    t = Table([headers, row1, row2, row3, row4], colWidths=[65, 175, 300])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, border_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_light])
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Recording Pro-Tips Box
    tips_title = Paragraph("<b>Director's Recording Tips:</b>", action_style)
    tips_text = Paragraph(
        "• <b>Mouse Movement:</b> Move the cursor deliberately; hover over the Gate 1/2 badges, the unified diff, and the 'PASS · exit 0' pill.<br/>"
        "• <b>Smooth Transitions:</b> Keep both <code>/autopilot</code> and <code>/office</code> open in tabs so switching takes 0.5 seconds.<br/>"
        "• <b>Key Talking Point:</b> Emphasize <i>'NVIDIA Nemotron 3.5'</i> and <i>'Docker container isolation with zero network'</i> to hit hackathon judging criteria.<br/>"
        "• <b>Pacing:</b> If Nemotron finishes in 20 seconds, pause for 3 seconds to let the audience appreciate the green pass badge before switching tabs.",
        body_style
    )
    tips_table = Table([[tips_title], [tips_text]], colWidths=[540])
    tips_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#fcd34d")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tips_table)

    doc.build(story)
    print("PDF successfully generated at:", output_path)

if __name__ == "__main__":
    build_pdf()
