# tools/pdf_tool.py
import fitz  # pymupdf
import pdfplumber
import io
import re
import difflib
from typing import Optional

class PDFResumeHandler:

    def extract_text_for_ai(self, file_path: str) -> str:
        """Extract clean plain text. Used to send to Gemini."""
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t:
                    pages.append(t)
        return "\n\n".join(pages)

    def rebuild_pdf_with_rewritten_text(
        self,
        original_path: str,
        original_text: str,
        rewritten_text: str,
    ) -> bytes:
        """
        Pixel-perfect PDF rebuild.
        Strategy:
        1. Build a line-level change map using difflib
        2. For every changed line, find its spans in the PDF
        3. Redact (white-box) just that line's area
        4. Reinsert new text at EXACT same position, font, size, color
        5. Never touch unchanged lines — they stay pixel-perfect
        """
        doc    = fitz.open(original_path)
        changes = self._build_change_map(original_text, rewritten_text)

        if not changes:
            # Nothing changed — return original
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            return buf.getvalue()

        for page in doc:
            self._process_page(page, changes)

        buf = io.BytesIO()
        doc.save(buf, garbage=4, deflate=True, clean=True)
        doc.close()
        return buf.getvalue()

    def _build_change_map(self, original: str, rewritten: str) -> dict:
        """
        Line-by-line diff. Returns {original_line: new_line} for changed lines only.
        Filters out lines that are headers, dates, names — we never change those.
        """
        DO_NOT_CHANGE = [
            r'^\d{4}\s*[-–]\s*(\d{4}|present)',  # dates
            r'^(Education|Experience|Projects|Skills|Certifications|Achievements)',  # section headers
            r'^(CGPA|GPA|GSEB)',                  # scores
            r'^\+?\d[\d\s\-()]{7,}',              # phone numbers
            r'^[A-Z][a-z]+\s[A-Z][a-z]+$',       # names (2 capitalized words)
            r'May\s+\d{4}',                       # month year dates
        ]

        orig_lines = [l for l in original.split('\n')  if l.strip()]
        new_lines  = [l for l in rewritten.split('\n') if l.strip()]

        changes = {}
        matcher = difflib.SequenceMatcher(None, orig_lines, new_lines, autojunk=False)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                orig_chunk = orig_lines[i1:i2]
                new_chunk  = new_lines[j1:j2]
                for k, orig_line in enumerate(orig_chunk):
                    if k >= len(new_chunk):
                        break
                    new_line = new_chunk[k]
                    if orig_line == new_line:
                        continue

                    # Never change protected lines
                    protected = False
                    for pattern in DO_NOT_CHANGE:
                        if re.search(pattern, orig_line, re.IGNORECASE):
                            protected = True
                            break
                    if protected:
                        continue

                    # Never add placeholder text
                    placeholders = ["[Email]", "[LinkedIn]", "[GitHub]", "[Phone]",
                                    "[Address]", "[Website]", "[URL]"]
                    if any(p in new_line for p in placeholders):
                        continue

                    # Only add if meaningfully different
                    if orig_line.strip() and new_line.strip():
                        changes[orig_line.strip()] = new_line.strip()

        return changes

    def _find_replacement(self, span_text: str, changes: dict) -> Optional[str]:
        """Find rewritten version for a span. Returns None if no change."""
        span_stripped = span_text.strip()
        if not span_stripped or len(span_stripped) < 4:
            return None

        # Exact match
        if span_stripped in changes:
            return changes[span_stripped]

        # Span is contained in a changed line
        for orig, new in changes.items():
            if span_stripped in orig and len(span_stripped) > 12:
                # Replace just this portion proportionally
                try:
                    start = orig.index(span_stripped)
                    ratio_s = start / len(orig)
                    ratio_e = (start + len(span_stripped)) / len(orig)
                    ns = int(ratio_s * len(new))
                    ne = int(ratio_e * len(new))
                    # Snap to word boundaries
                    while ns > 0 and new[ns-1] != ' ':
                        ns -= 1
                    while ne < len(new) and new[ne] != ' ':
                        ne += 1
                    candidate = new[ns:ne].strip()
                    if candidate and len(candidate) > 2:
                        return candidate
                except Exception:
                    pass

            # Changed line contained in span
            if orig in span_stripped and len(orig) > 12:
                return span_stripped.replace(orig, new)

        return None

    def _get_font_name(self, pdf_font: str, flags: int) -> str:
        """Map PDF font name to PyMuPDF built-in. Preserves bold/italic."""
        name    = pdf_font.lower()
        is_bold = bool(flags & 16) or "bold" in name
        is_ital = bool(flags & 2)  or "italic" in name or "oblique" in name

        if any(x in name for x in ["helv", "arial", "calibri", "sans", "gothic", "roboto"]):
            if is_bold and is_ital: return "hebi"
            if is_bold:             return "hebo"
            if is_ital:             return "heit"
            return "helv"
        elif any(x in name for x in ["times", "roman", "serif", "garamond", "georgia"]):
            if is_bold and is_ital: return "tibi"
            if is_bold:             return "tibo"
            if is_ital:             return "tiit"
            return "tiro"
        elif any(x in name for x in ["cour", "mono", "consol", "lucida"]):
            if is_bold and is_ital: return "cobi"
            if is_bold:             return "cobo"
            if is_ital:             return "coit"
            return "cour"

        # Default fallback
        if is_bold and is_ital: return "hebi"
        if is_bold:             return "hebo"
        if is_ital:             return "heit"
        return "helv"

    def _int_to_rgb(self, color) -> tuple:
        """Convert PyMuPDF color to normalized RGB."""
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            return tuple(min(1.0, v / 255 if v > 1 else v) for v in color[:3])
        if isinstance(color, float):
            return (color, color, color)
        if isinstance(color, int):
            return ((color >> 16 & 0xFF) / 255,
                    (color >>  8 & 0xFF) / 255,
                    (color        & 0xFF) / 255)
        return (0.0, 0.0, 0.0)

    def _get_bg_color(self, page: fitz.Page, rect: fitz.Rect) -> tuple:
        """Sample background color at a location. Most resumes are white."""
        try:
            clip = fitz.Rect(rect.x0, rect.y0, rect.x0 + 3, rect.y0 + 3)
            mat  = fitz.Matrix(1, 1)
            pix  = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
            s    = pix.samples
            if len(s) >= 3:
                r, g, b = s[0] / 255, s[1] / 255, s[2] / 255
                # If very dark (header area), return that color
                if r < 0.15 and g < 0.15 and b < 0.15:
                    return (r, g, b)  # dark header bg
                # Otherwise white
                return (1.0, 1.0, 1.0)
        except Exception:
            pass
        return (1.0, 1.0, 1.0)

    def _process_page(self, page: fitz.Page, changes: dict):
        """Process a single PDF page — find changed spans, redact, reinsert."""
        blocks = page.get_text(
            "rawdict",
            flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
        ).get("blocks", [])

        replacements = []  # collect all replacements first, then apply

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                # Reconstruct line text from spans
                line_text = "".join(
                    s.get("text", "") for s in line.get("spans", [])
                ).strip()
                if not line_text:
                    continue

                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if not span_text or len(span_text) < 3:
                        continue

                    new_text = self._find_replacement(span_text, changes)
                    if new_text is None or new_text == span_text:
                        continue

                    # CRITICAL: truncate new text to fit same width
                    # Calculate chars per pixel ratio from original
                    bbox      = fitz.Rect(span["bbox"])
                    orig_width = bbox.width
                    orig_chars = len(span_text)
                    if orig_chars > 0 and orig_width > 0:
                        chars_per_px = orig_chars / orig_width
                        max_chars    = int(orig_width * chars_per_px * 1.15)  # 15% overflow ok
                        if len(new_text) > max_chars:
                            new_text = new_text[:max_chars].rsplit(" ", 1)[0] + "..."

                    replacements.append({
                        "bbox":      bbox,
                        "new_text":  new_text,
                        "font":      self._get_font_name(span.get("font",""), span.get("flags", 0)),
                        "size":      span.get("size", 11),
                        "color":     self._int_to_rgb(span.get("color", 0)),
                        "origin_y":  span.get("origin", (bbox.x0, bbox.y1))[1],
                    })

        # Apply all replacements
        for rep in replacements:
            bbox = rep["bbox"]

            # 1. Sample background
            bg = self._get_bg_color(page, bbox)

            # 2. Erase original text
            erase = fitz.Rect(
                bbox.x0 - 0.5,
                bbox.y0,
                bbox.x1 + 1.0,
                bbox.y1 + 0.5
            )
            shape = page.new_shape()
            shape.draw_rect(erase)
            shape.finish(color=bg, fill=bg, width=0)
            shape.commit()

            # 3. Insert new text at EXACT original baseline
            try:
                page.insert_text(
                    point=fitz.Point(bbox.x0, rep["origin_y"]),
                    text=rep["new_text"],
                    fontname=rep["font"],
                    fontsize=rep["size"],  # EXACT original size — never change this
                    color=rep["color"],
                    render_mode=0,
                )
            except Exception:
                # Font registration fallback
                try:
                    page.insert_text(
                        point=fitz.Point(bbox.x0, rep["origin_y"]),
                        text=rep["new_text"],
                        fontname="helv",
                        fontsize=rep["size"],
                        color=rep["color"],
                    )
                except Exception:
                    pass  # Skip this span — leave original


pdf_handler = PDFResumeHandler()
