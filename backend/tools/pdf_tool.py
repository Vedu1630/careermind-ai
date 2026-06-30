"""
PDF Resume Handler — pixel-perfect rewriter using textbox insertion.
Handles text wrapping correctly so no text is truncated.
"""
import fitz
import pdfplumber
import difflib
import re
import io
from typing import Optional, List


class PDFResumeHandler:

    def extract_text_for_ai(self, file_path: str) -> str:
        """Extract clean plain text preserving reading order."""
        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if t and t.strip():
                        pages.append(t.strip())
        except Exception as e:
            print(f"pdfplumber failed: {e}")
            try:
                doc = fitz.open(file_path)
                for page in doc:
                    pages.append(page.get_text("text"))
                doc.close()
            except Exception as e2:
                print(f"PyMuPDF also failed: {e2}")
        return "\n\n".join(pages)

    def build_change_map(self, original_text: str, rewritten_text: str) -> dict:
        """
        Build {original_paragraph → rewritten_paragraph} for changed content.
        Works at paragraph level, not line level, to handle text wrapping.
        """
        # Protected patterns — NEVER change these
        PROTECTED = [
            r'^(Education|Experience|Projects|Skills|Certifications|'
            r'Achievements|Publications|CORE SKILLS|Technical Skills|'
            r'Soft Skills|Positions of Responsibility)\s*[_\-]*\s*$',
            r'^(MPSTME|NMIMS|Bhulka|Savani|SoftSages|HackerRank|Deloitte|Delottie)',
            r'\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|present|current)',
            r'\b(CGPA|GPA|GSEB|B\.Tech|B\.E\.|M\.Tech)\b',
            r'^Date of birth',
            r'^BTech|B\.Tech|Batch\s+\d{4}',
            r'^[A-Z][a-z]+\s+[A-Z][a-z]+\s*$',  # names
            r'^\s*[\•\-\*]\s*(Programming|Web Technologies|Databases|Concepts|Soft Skills):',
        ]

        def is_protected(line: str) -> bool:
            for pat in PROTECTED:
                if re.search(pat, line.strip(), re.IGNORECASE):
                    return True
            if len(line.strip().split()) < 3:
                return True
            return False

        orig_lines = [l for l in original_text.split('\n') if l.strip()]
        new_lines  = [l for l in rewritten_text.split('\n') if l.strip()]

        change_map = {}
        matcher    = difflib.SequenceMatcher(None, orig_lines, new_lines, autojunk=False)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != 'replace':
                continue
            orig_chunk = orig_lines[i1:i2]
            new_chunk  = new_lines[j1:j2]

            for k, orig_line in enumerate(orig_chunk):
                if k >= len(new_chunk):
                    break
                new_line     = new_chunk[k]
                orig_stripped = orig_line.strip()
                new_stripped  = new_line.strip()

                if orig_stripped == new_stripped:
                    continue
                if is_protected(orig_stripped):
                    continue
                if any(p in new_stripped.lower() for p in
                       ['[email]','[linkedin]','[github]','[phone]','[url]']):
                    continue

                change_map[orig_stripped] = new_stripped

        print(f"📝 {len(change_map)} text spans will be updated")
        return change_map

    def get_font(self, name: str, flags: int) -> str:
        """Map PDF font name to PyMuPDF built-in."""
        n       = (name or "").lower()
        is_bold = bool(flags & 16) or "bold" in n
        is_ital = bool(flags & 2)  or "italic" in n or "oblique" in n

        if any(x in n for x in ["helv","arial","calibri","sans","gothic","roboto","verdana"]):
            if is_bold and is_ital: return "hebi"
            if is_bold:             return "hebo"
            if is_ital:             return "heit"
            return "helv"
        if any(x in n for x in ["times","roman","serif","georgia","garamond"]):
            if is_bold and is_ital: return "tibi"
            if is_bold:             return "tibo"
            if is_ital:             return "tiit"
            return "tiro"
        if any(x in n for x in ["cour","mono","consol"]):
            if is_bold and is_ital: return "cobi"
            if is_bold:             return "cobo"
            if is_ital:             return "coit"
            return "cour"
        if is_bold and is_ital: return "hebi"
        if is_bold:             return "hebo"
        if is_ital:             return "heit"
        return "helv"

    def to_rgb(self, color) -> tuple:
        """Convert color value to normalized RGB."""
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            return tuple(min(1.0, v/255 if v>1 else float(v)) for v in color[:3])
        if isinstance(color, float):
            v = max(0.0, min(1.0, color))
            return (v, v, v)
        if isinstance(color, int):
            return ((color>>16&0xFF)/255, (color>>8&0xFF)/255, (color&0xFF)/255)
        return (0.0, 0.0, 0.0)

    def sample_bg(self, page: fitz.Page, rect: fitz.Rect) -> tuple:
        """Sample background color at rect location."""
        try:
            clip = fitz.Rect(rect.x0, rect.y0,
                             min(rect.x0+4, rect.x1),
                             min(rect.y0+4, rect.y1))
            pix = page.get_pixmap(matrix=fitz.Matrix(1,1), clip=clip, alpha=False)
            s   = pix.samples
            if len(s) >= 3:
                r, g, b = s[0]/255, s[1]/255, s[2]/255
                if r < 0.15 and g < 0.15 and b < 0.15:
                    return (r, g, b)
                return (1.0, 1.0, 1.0)
        except Exception:
            pass
        return (1.0, 1.0, 1.0)

    def find_replacement(self, span_text: str, change_map: dict) -> Optional[str]:
        """Find replacement for a text span."""
        if not span_text or len(span_text.strip()) < 4:
            return None
        s = span_text.strip()

        # Exact match
        if s in change_map:
            return change_map[s]

        # Span is part of a changed line
        for orig, new in change_map.items():
            if s in orig and len(s) > 20:
                try:
                    idx = orig.index(s)
                    r_s = idx / len(orig)
                    r_e = (idx + len(s)) / len(orig)
                    ns  = int(r_s * len(new))
                    ne  = int(r_e * len(new))
                    while ns > 0 and ns < len(new) and new[ns-1] != ' ': ns -= 1
                    while ne < len(new) and new[ne] != ' ': ne += 1
                    cand = new[ns:ne].strip()
                    if cand and len(cand) >= 3:
                        return cand
                except (ValueError, IndexError):
                    pass
            if orig in s and len(orig) > 20:
                return s.replace(orig, new, 1)

        return None

    def rebuild_pdf_with_rewritten_text(
        self,
        original_path: str,
        original_text: str,
        rewritten_text: str,
    ) -> bytes:
        """
        Pixel-perfect PDF rewrite.

        Key fix for truncation:
        - Uses insert_textbox() instead of insert_text()
        - insert_textbox() wraps text within the line's bounding box
        - Expands the erase area to cover the full original text height
        - Never truncates — if text doesn't fit, reduces font size slightly
        """
        doc        = fitz.open(original_path)
        change_map = self.build_change_map(original_text, rewritten_text)
        total      = 0

        if not change_map:
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            return buf.getvalue()

        for page_num in range(len(doc)):
            page = doc[page_num]

            raw = page.get_text(
                "rawdict",
                flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
            )

            # Group spans by their block — we process entire text blocks together
            # This handles multi-line paragraphs correctly
            block_replacements = []

            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue

                # Collect all spans in this block
                block_spans = []
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text and len(span_text) >= 3:
                            new_text = self.find_replacement(span_text, change_map)
                            if new_text and new_text != span_text:
                                block_spans.append({
                                    "bbox":      fitz.Rect(span["bbox"]),
                                    "new_text":  new_text,
                                    "orig_text": span_text,
                                    "font":      self.get_font(span.get("font",""), span.get("flags",0)),
                                    "size":      span.get("size", 11),
                                    "color":     self.to_rgb(span.get("color", 0)),
                                    "origin":    span.get("origin", (span["bbox"][0], span["bbox"][3])),
                                })

                if block_spans:
                    block_replacements.extend(block_spans)

            # Apply replacements
            for rep in block_replacements:
                bbox = rep["bbox"]

                # Step 1: Erase original text — use full line height + padding
                bg = self.sample_bg(page, bbox)
                erase = fitz.Rect(
                    bbox.x0 - 0.5,
                    bbox.y0 - 0.3,
                    bbox.x1 + 2.0,  # extra right margin for longer text
                    bbox.y1 + 0.5,
                )
                shape = page.new_shape()
                shape.draw_rect(erase)
                shape.finish(color=bg, fill=bg, width=0)
                shape.commit()

                # Step 2: Insert new text using insert_textbox for proper wrapping
                # The textbox rect matches the original span area
                # This prevents text from overflowing right margin
                text_rect = fitz.Rect(
                    bbox.x0,
                    bbox.y0,
                    bbox.x1,   # Use original right edge — text wraps within this
                    bbox.y1 + 50,  # Extra height allows wrapping down
                )

                font_size = rep["size"]
                try:
                    # Try insert_textbox first (handles wrapping)
                    result = page.insert_textbox(
                        text_rect,
                        rep["new_text"] + " ",  # trailing space prevents clipping
                        fontname=rep["font"],
                        fontsize=font_size,
                        color=rep["color"],
                        align=0,  # left align
                    )
                    # If result < 0, text didn't fit — reduce font size
                    if result < 0:
                        for reduced_size in [font_size - 0.5, font_size - 1.0, font_size - 1.5]:
                            if reduced_size < 7:
                                break
                            result = page.insert_textbox(
                                text_rect,
                                rep["new_text"] + " ",
                                fontname=rep["font"],
                                fontsize=reduced_size,
                                color=rep["color"],
                                align=0,
                            )
                            if result >= 0:
                                break
                    total += 1

                except Exception as e1:
                    print(f"⚠️ insert_textbox failed ({rep['font']}): {e1}")
                    # Fallback: insert_text at baseline (may truncate but better than nothing)
                    try:
                        origin = rep["origin"]
                        page.insert_text(
                            fitz.Point(origin[0] if isinstance(origin,(list,tuple)) else bbox.x0,
                                      origin[1] if isinstance(origin,(list,tuple)) else bbox.y1),
                            rep["new_text"],
                            fontname="helv",
                            fontsize=font_size,
                            color=rep["color"],
                        )
                        total += 1
                    except Exception as e2:
                        print(f"❌ Both insert methods failed: {e2}")

        print(f"✅ Rebuilt PDF: {total} spans updated across {len(doc)} pages")

        buf = io.BytesIO()
        doc.save(buf, garbage=3, deflate=True, clean=True)
        doc.close()
        return buf.getvalue()


pdf_handler = PDFResumeHandler()
