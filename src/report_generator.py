# server/report_generator.py
import logging
import sys
import shutil
from pathlib import Path
from datetime import datetime
from fpdf import FPDF

logger = logging.getLogger("AI-Search-Report")

class OSINTReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.font_family_name = "Arial"
        self.use_cyrillic = False

    def header(self):
        # Draw a beautiful top accent bar
        self.set_fill_color(108, 92, 231)  # Premium royal indigo (#6c5ce7)
        self.rect(0, 0, 210, 15, "F")
        
        # Header text
        self.set_y(4)
        self.set_text_color(255, 255, 255)
        self.set_font(self.font_family_name, "B", 10)
        self.cell(0, 8, "AI OSINT DEEP RESEARCH EXECUTIVE BRIEF", border=0, ln=1, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        # Use built-in Helvetica for italic style in footer as it contains only English characters
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(127, 140, 141)
        self.cell(0, 10, f"Page {self.page_no()} | Confidential AI Research Summary | {datetime.now().strftime('%Y-%m-%d')}", 0, 0, "C")

def setup_local_fonts():
    """Sets up local Cyrillic fonts in the data/fonts folder to avoid PermissionError on Windows."""
    local_fonts_dir = Path(__file__).parent.parent / "data" / "fonts"
    local_fonts_dir.mkdir(parents=True, exist_ok=True)
    
    loaded = {}
    if sys.platform == "win32":
        sys_fonts_dir = Path("C:\\Windows\\Fonts")
        for font_name, file_name in [("ArialCyr", "arial.ttf"), ("ArialCyrBd", "arialbd.ttf")]:
            sys_path = sys_fonts_dir / file_name
            local_path = local_fonts_dir / file_name
            if sys_path.exists():
                try:
                    if not local_path.exists() or local_path.stat().st_size != sys_path.stat().st_size:
                        shutil.copy(sys_path, local_path)
                    loaded[font_name] = local_path
                except Exception as e:
                    logger.warning(f"Could not copy system font {file_name}: {e}")
    
    # Check if local files are present
    for fkey, fname in [("regular", "arial.ttf"), ("bold", "arialbd.ttf")]:
        local_path = local_fonts_dir / fname
        if local_path.exists():
            loaded[fkey] = local_path
    return loaded

def clean_txt_cyr(text: str, use_cyrillic: bool) -> str:
    """Helper to convert unicode quotes or safely sanitize text for non-Cyrillic fallbacks."""
    if not text:
        return ""
    # Replace common MS Word quotes that crash PyFPDF latin-1
    text = text.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-")
    if use_cyrillic:
        return text
    # Fallback: strip Cyrillic to avoid FPDF codec crash
    return text.encode('latin-1', 'ignore').decode('latin-1')

def render_markdown_text(pdf, text: str, font_name: str, use_cyrillic: bool):
    """Parses simple Markdown blocks and inline bolding and draws it beautifully to the PDF."""
    lines = text.split("\n")
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            pdf.ln(3)
            continue
            
        # 1. Headings (H3)
        if line_strip.startswith("### "):
            pdf.ln(2)
            pdf.set_font(font_name, "B", 12.5)
            pdf.set_text_color(108, 92, 231)  # Amethyst accent color
            pdf.multi_cell(0, 6, clean_txt_cyr(line_strip[4:], use_cyrillic))
            pdf.ln(1.5)
            pdf.set_text_color(0, 0, 0)
            continue
            
        # 2. Headings (H1/H2)
        elif line_strip.startswith("## ") or line_strip.startswith("# "):
            header_text = line_strip[3:] if line_strip.startswith("## ") else line_strip[2:]
            pdf.ln(3)
            pdf.set_font(font_name, "B", 14)
            pdf.set_text_color(108, 92, 231)
            pdf.multi_cell(0, 7, clean_txt_cyr(header_text, use_cyrillic))
            pdf.ln(2.5)
            pdf.set_text_color(0, 0, 0)
            continue
            
        # 3. Blockquotes
        if line_strip.startswith("> "):
            pdf.set_fill_color(245, 246, 250)
            pdf.set_left_margin(15)
            # Avoid using italic style 'I' for Cyrillic ArialCyr as it's not registered
            pdf.set_font(font_name, "", 10)
            pdf.multi_cell(0, 5, clean_txt_cyr(line_strip[2:], use_cyrillic), fill=True)
            pdf.set_left_margin(10)
            pdf.ln(2)
            continue
            
        # 4. List bullets
        if line_strip.startswith("- ") or line_strip.startswith("* ") or line_strip.startswith("• "):
            bullet_content = line_strip[2:]
            pdf.set_left_margin(15)
            pdf.set_font(font_name, "", 10.5)
            # Safe dash bullet to prevent font subset index errors
            pdf.write(5.5, "- ")
            parts = bullet_content.split("**")
            for idx, part in enumerate(parts):
                if idx % 2 == 1:
                    pdf.set_font(font_name, "B", 10.5)
                else:
                    pdf.set_font(font_name, "", 10.5)
                pdf.write(5.5, clean_txt_cyr(part, use_cyrillic))
            pdf.ln(5.5)
            pdf.set_left_margin(10)
            continue
            
        # 5. Regular paragraph with bold support
        pdf.set_font(font_name, "", 10.5)
        parts = line_strip.split("**")
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                pdf.set_font(font_name, "B", 10.5)
            else:
                pdf.set_font(font_name, "", 10.5)
            pdf.write(5.5, clean_txt_cyr(part, use_cyrillic))
        pdf.ln(5.5)

def generate_pdf_report(query: str, answer: str, sources: list, output_path: Path, messages: list = None):
    """Generates a premium, beautiful PDF report supporting Cyrillic characters and multi-turn transcript."""
    try:
        pdf = OSINTReport()
        font_name = "Arial"
        use_cyrillic = False
        
        # Load local TrueType fonts to avoid PermissionError in standard system directories
        try:
            fonts = setup_local_fonts()
            if "regular" in fonts and "bold" in fonts:
                pdf.add_font("ArialCyr", "", str(fonts["regular"]), uni=True)
                pdf.add_font("ArialCyr", "B", str(fonts["bold"]), uni=True)
                font_name = "ArialCyr"
                use_cyrillic = True
                logger.info("Successfully loaded local Arial TrueType fonts for Cyrillic support.")
        except Exception as e:
            logger.warning(f"Could not load local TrueType Cyrillic fonts: {e}")
            
        pdf.font_family_name = font_name
        pdf.use_cyrillic = use_cyrillic
        
        pdf.add_page()
        
        # Title Section
        pdf.set_font(font_name, "B", 16)
        pdf.set_text_color(44, 62, 80)
        pdf.multi_cell(0, 9, clean_txt_cyr(f"Звіт дослідження: {query}", use_cyrillic))
        pdf.ln(2)
        
        # Metadata Card
        pdf.set_font(font_name, "", 9)
        pdf.set_text_color(127, 140, 141)
        pdf.cell(0, 5, f"Згенеровано: {datetime.now().strftime('%Y-%m-%d %H:%M')} | КНУ ім. Тараса Шевченка", ln=1)
        pdf.ln(8)
        
        # Seed messages for backward compatibility if none are provided
        if not messages:
            messages = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": answer}
            ]
            
        # Draw Dialogue Section
        pdf.set_font(font_name, "B", 13)
        pdf.set_text_color(108, 92, 231)
        pdf.cell(0, 10, "Хронологія аналізу", ln=1)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        for index, msg in enumerate(messages, 1):
            if msg.get("role") == "user":
                # Render User Message Card
                pdf.set_fill_color(248, 247, 255)  # Shaded purple background
                pdf.set_text_color(108, 92, 231)   # Amethyst text
                pdf.set_font(font_name, "B", 10.5)
                pdf.multi_cell(0, 6, clean_txt_cyr(f"Запит {index // 2 + 1}: {msg.get('content')}", use_cyrillic), border="L", fill=True)
                pdf.ln(3)
            else:
                # Render Assistant Message
                pdf.set_text_color(44, 62, 80)
                render_markdown_text(pdf, msg.get("content", ""), font_name, use_cyrillic)
                pdf.ln(6)
                
        # Draw Sources Section
        pdf.add_page()
        pdf.set_font(font_name, "B", 13)
        pdf.set_text_color(108, 92, 231)
        pdf.cell(0, 10, "Верифіковані джерела інформації", ln=1)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)
        
        pdf.set_font(font_name, "", 10)
        for i, source in enumerate(sources, 1):
            title = clean_txt_cyr(source.get("title", "Джерело"), use_cyrillic)
            url = source.get("url", "")
            
            # Bullet layout for sources
            pdf.set_font(font_name, "B", 10)
            pdf.set_text_color(44, 62, 80)
            pdf.write(5.5, f"[{i}] {title}\n")
            
            # Interactive blue link
            pdf.set_font(font_name, "", 9.5)
            pdf.set_text_color(9, 132, 227)
            pdf.write(5.5, f"      Посилання: {url}\n", url)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(3)
            
        pdf.output(str(output_path))
        logger.info(f"Stunning PDF Report successfully generated at: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate beautiful PDF report: {e}", exc_info=True)
        return False

def parse_markdown_to_html(md: str) -> str:
    """A clean, fast Python markdown parser that transforms standard MD blocks into beautiful, secure HTML."""
    if not md:
        return ""
    
    # Standardize newlines
    md = md.replace("\r\n", "\n")
    
    # Escape HTML to prevent XSS
    html = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Let's do it via regex-like splits
    lines = html.split("\n")
    processed_lines = []
    
    in_list = False
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            if in_list:
                processed_lines.append("</ul>")
                in_list = False
            processed_lines.append("<br>")
            continue
            
        # Headers
        if line_strip.startswith("### "):
            if in_list:
                processed_lines.append("</ul>")
                in_list = False
            processed_lines.append(f"<h3>{line_strip[4:]}</h3>")
            continue
        elif line_strip.startswith("## ") or line_strip.startswith("# "):
            if in_list:
                processed_lines.append("</ul>")
                in_list = False
            header_text = line_strip[3:] if line_strip.startswith("## ") else line_strip[2:]
            processed_lines.append(f"<h2>{header_text}</h2>")
            continue
            
        # Blockquotes
        if line_strip.startswith("> "):
            if in_list:
                processed_lines.append("</ul>")
                in_list = False
            processed_lines.append(f"<blockquote>{line_strip[2:]}</blockquote>")
            continue
            
        # List bullets
        if line_strip.startswith("- ") or line_strip.startswith("* ") or line_strip.startswith("• "):
            if not in_list:
                processed_lines.append("<ul>")
                in_list = True
            bullet_content = line_strip[2:]
            processed_lines.append(f"<li>{bullet_content}</li>")
            continue
            
        # Standard paragraph
        if in_list:
            processed_lines.append("</ul>")
            in_list = False
            
        processed_lines.append(f"<p>{line_strip}</p>")
        
    if in_list:
        processed_lines.append("</ul>")
        
    html = "\n".join(processed_lines)
    
    # Parse bold keywords
    # Using simple split to avoid complex regex engines
    bold_parts = html.split("**")
    html_bold = []
    for idx, part in enumerate(bold_parts):
        if idx % 2 == 1:
            html_bold.append(f"<strong>{part}</strong>")
        else:
            html_bold.append(part)
    html = "".join(html_bold)
    
    # Parse cite badges [S1], [S2] to interactive nodes
    import re
    html = re.sub(r'\[(S\d+)\]', r'<span class="cite-badge" data-target="\1">\1</span>', html)
    
    # Clean up empty paragraphs
    html = html.replace("<p></p>", "").replace("<p><br></p>", "")
    return html

def generate_shareable_html(query: str, answer: str, sources: list, output_path: Path, messages: list = None):
    """Generates a standalone interactive, gorgeous dark-glass HTML page for research sessions."""
    
    if not messages:
        messages = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": answer}
        ]
        
    # Generate Dialogue HTML
    dialogue_html = ""
    for index, msg in enumerate(messages, 1):
        role = msg.get("role")
        content = msg.get("content", "")
        
        if role == "user":
            dialogue_html += f"""
            <div class="message-bubble user-bubble">
                <div class="bubble-header"><i class="lucide-user"></i> Запит користувача</div>
                <div class="bubble-content">{content}</div>
            </div>
            """
        else:
            parsed_content = parse_markdown_to_html(content)
            dialogue_html += f"""
            <div class="message-bubble ai-bubble">
                <div class="bubble-header"><i class="lucide-cpu"></i> Аналіз асистента AI Search</div>
                <div class="bubble-content">{parsed_content}</div>
            </div>
            """

    # Generate Sources HTML
    sources_html = ""
    for i, s in enumerate(sources, 1):
        title = s.get("title", "Джерело")
        url = s.get("url", "")
        snippet = s.get("content") or s.get("snippet") or "Зміст джерела не збережено."
        score = s.get("relevance_score", 0.0)
        score_percent = int(score * 100) if score else 0
        s_id = s.get("id") or f"S{i}"
        
        sources_html += f"""
        <div class="source-card" id="card-{s_id}">
            <div class="source-card-header">
                <span class="source-badge">[{s_id}]</span>
                <span class="source-score">Релевантність: {score_percent}%</span>
            </div>
            <div class="source-card-title">{title}</div>
            <div class="source-card-snippet">{snippet}</div>
            <a class="source-link" href="{url}" target="_blank">Відкрити першоджерело <i class="lucide-external-link"></i></a>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI OSINT Research: {query}</title>
    
    <!-- Premium Web Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    
    <style>
        :root {{
            --bg-main: #07050d;
            --bg-card: rgba(25, 21, 46, 0.45);
            --accent-purple: #a855f7;
            --accent-blue: #3b82f6;
            --border-glow: rgba(168, 85, 247, 0.15);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background: radial-gradient(circle at top left, #0e0a1e, var(--bg-main));
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            padding: 40px 20px;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}

        /* Premium Header */
        header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}

        .header-badge {{
            display: inline-flex;
            align-items: center;
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.15), rgba(59, 130, 246, 0.15));
            border: 1px solid rgba(168, 85, 247, 0.3);
            color: #d8b4fe;
            padding: 6px 16px;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
            margin-bottom: 16px;
            font-family: 'Outfit', sans-serif;
        }}

        h1 {{
            font-size: 2.2rem;
            background: linear-gradient(135deg, #f8fafc, #c084fc, #60a5fa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
        }}

        .meta-row {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        /* Timeline and bubbles */
        .timeline-section {{
            margin-bottom: 50px;
        }}

        .section-title {{
            font-size: 1.4rem;
            margin-bottom: 24px;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
            border-left: 4px solid var(--accent-purple);
            padding-left: 12px;
        }}

        .message-bubble {{
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(12px);
        }}

        .user-bubble {{
            border-left: 4px solid var(--accent-purple);
            background: rgba(168, 85, 247, 0.04);
        }}

        .ai-bubble {{
            border-left: 4px solid var(--accent-blue);
        }}

        .bubble-header {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .user-bubble .bubble-header {{
            color: #c084fc;
        }}

        .ai-bubble .bubble-header {{
            color: #60a5fa;
        }}

        .bubble-content {{
            font-size: 1.05rem;
            color: #e2e8f0;
        }}

        .bubble-content p {{
            margin-bottom: 16px;
        }}

        .bubble-content h3 {{
            margin: 24px 0 12px 0;
            color: #d8b4fe;
            font-size: 1.25rem;
        }}

        .bubble-content ul {{
            margin-left: 24px;
            margin-bottom: 16px;
        }}

        .bubble-content li {{
            margin-bottom: 8px;
        }}

        .bubble-content blockquote {{
            background: rgba(255, 255, 255, 0.03);
            border-left: 4px solid rgba(255, 255, 255, 0.2);
            padding: 12px 20px;
            margin: 16px 0;
            font-style: italic;
            border-radius: 4px;
        }}

        /* Cite Badges */
        .cite-badge {{
            background: rgba(168, 85, 247, 0.18);
            border: 1px solid rgba(168, 85, 247, 0.4);
            color: #d8b4fe;
            font-size: 0.75rem;
            font-weight: bold;
            padding: 1px 6px;
            border-radius: 4px;
            margin: 0 3px;
            cursor: pointer;
            transition: all 0.2s ease;
            vertical-align: super;
        }}

        .cite-badge:hover {{
            background: var(--accent-purple);
            color: white;
            box-shadow: 0 0 10px rgba(168, 85, 247, 0.6);
        }}

        /* Sources Grid */
        .sources-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }}

        @media (min-width: 768px) {{
            .sources-grid {{
                grid-template-columns: 1fr 1fr;
            }}
        }}

        .source-card {{
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(12px);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
        }}

        .source-card:hover, .source-card.highlight {{
            border-color: var(--accent-purple);
            box-shadow: 0 0 25px rgba(168, 85, 247, 0.25);
            transform: translateY(-4px);
        }}

        .source-card.highlight {{
            animation: highlightGlow 2.5s ease-in-out;
        }}

        @keyframes highlightGlow {{
            0%, 100% {{ border-color: rgba(255,255,255,0.08); }}
            50% {{ border-color: #a855f7; box-shadow: 0 0 30px rgba(168, 85, 247, 0.5); }}
        }}

        .source-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}

        .source-badge {{
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            color: #60a5fa;
            font-size: 0.8rem;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 6px;
        }}

        .source-score {{
            font-size: 0.8rem;
            color: #10b981;
            font-weight: 500;
        }}

        .source-card-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: white;
            margin-bottom: 12px;
            line-height: 1.4;
        }}

        .source-card-snippet {{
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 20px;
            flex-grow: 1;
        }}

        .source-link {{
            color: #60a5fa;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-top: auto;
            align-self: flex-start;
        }}

        .source-link:hover {{
            text-decoration: underline;
        }}

        footer.page-footer {{
            text-align: center;
            margin-top: 60px;
            padding-top: 30px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}

        /* Print optimization styles - Enterprise Standard */
        @media print {{
            body {{
                background: #ffffff !important;
                color: #111111 !important;
                padding: 0 !important;
            }}
            .container {{
                max-width: 100% !important;
            }}
            .message-bubble, .source-card {{
                background: #ffffff !important;
                color: #111111 !important;
                border: 1px solid #e2e8f0 !important;
                box-shadow: none !important;
                page-break-inside: avoid;
            }}
            .user-bubble {{
                border-left: 4px solid #6c5ce7 !important;
                background: #f8fafc !important;
            }}
            h1, h2, h3, h4 {{
                color: #111111 !important;
                background: none !important;
                -webkit-text-fill-color: initial !important;
            }}
            .cite-badge {{
                background: #e2e8f0 !important;
                color: #111111 !important;
                border: 1px solid #cbd5e1 !important;
            }}
            .source-link {{
                color: #2563eb !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        
        <header>
            <div class="header-badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px; display:inline-block; vertical-align:middle;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                OSINT DEEP RESEARCH EXECUTIVE BRIEF
            </div>
            <h1>Звіт з пошуку: {query}</h1>
            <div class="meta-row">
                Згенеровано: {datetime.now().strftime('%Y-%m-%d %H:%M')} | КНУ ім. Тараса Шевченка
            </div>
        </header>

        <!-- Chronology of research -->
        <section class="timeline-section">
            <h2 class="section-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:middle; margin-right:4px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Аналітичний лог сесії
            </h2>
            {dialogue_html}
        </section>

        <!-- Sources Section -->
        <section class="sources-section">
            <h2 class="section-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:middle; margin-right:4px;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                Верифіковані джерела
            </h2>
            <div class="sources-grid">
                {sources_html}
            </div>
        </section>

        <footer class="page-footer">
            Усі права захищено. AI OSINT Deep Research Tool | 2026
        </footer>

    </div>

    <!-- Script to handle dynamic interactive actions -->
    <script>
        document.addEventListener("DOMContentLoaded", () => {{
            // Add interaction on cite badges to highlight matching sources
            const badges = document.querySelectorAll(".cite-badge");
            badges.forEach(badge => {{
                badge.addEventListener("click", () => {{
                    const targetId = badge.getAttribute("data-target");
                    const card = document.getElementById("card-" + targetId);
                    if (card) {{
                        card.scrollIntoView({{ behavior: "smooth", block: "center" }});
                        card.classList.add("highlight");
                        setTimeout(() => {{
                            card.classList.remove("highlight");
                        }}, 2500);
                    }}
                }});
            }});
        }});
    </script>
</body>
</html>
"""
    try:
        output_path.write_text(html_template, encoding="utf-8")
        logger.info(f"Stunning Shareable HTML Page successfully generated at: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate beautiful HTML report: {e}")
        return False
