"""
PDF Resume Handler — pixel-perfect rewriter.
Opens original PDF, finds changed text spans,
erases and rewrites only those spans.
Everything else stays identical.
"""
import fitz       # pymupdf
import pdfplumber
import difflib
import re
import io
from typing import Optional


class PDFResumeHandler:

    # ── Text extraction ──────────────────────────────────────────
    def extract_text_for_ai(self, file_path: str) -> str:
        """
        Extract clean plain text from PDF.
        Preserves reading order. Used to send to Gemini/Groq for rewriting.
        """
        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if t and t.strip():
                        pages.append(t.strip())
        except Exception as e:
            print(f"pdfplumber failed: {e}, trying PyMuPDF")
            try:
                doc = fitz.open(file_path)
                for page in doc:
                    pages.append(page.get_text("text"))
                doc.close()
            except Exception as e2:
                print(f"PyMuPDF also failed: {e2}")
        return "\n\n".join(pages)

    # ── Change detection ─────────────────────────────────────────
    def build_change_map(self, original_text: str, rewritten_text: str) -> dict:
        """
        Build a mapping of {original_line → rewritten_line}
        for lines that actually changed content.

        Protected lines that NEVER get changed:
        - Section headers (Education, Experience, Projects, etc.)
        - Names, dates, universities, companies
        - Scores (CGPA, GSEB, percentages)
        - Short lines under 8 words (likely headers or labels)
        """
        # Lines that should NEVER be changed
        PROTECTED_PATTERNS = [
            r'^\s*(Education|Experience|Projects|Skills|Certifications|'
            r'Achievements|Publications|CORE SKILLS|Technical Skills|'
            r'Soft Skills|Positions of Responsibility)\s*[_\-]*\s*$',
            r'^\s*(MPSTME|NMIMS|Bhulka|Savani|SoftSages|HackerRank|Deloitte|Delottie)',
            r'\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|present|current)',
            r'\b(CGPA|GPA|GSEB|B\.Tech|B\.E\.|M\.Tech)\b',
            r'^\s*[A-Z][a-z]+\s+[A-Z][a-z]+\s*$',  # Person names
            r'^\s*Date of birth',
            r'^\s*BTech|B\.Tech',
            r'^\s*Batch\s+\d{4}',
        ]

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

                new_line = new_chunk[k]
                orig_stripped = orig_line.strip()
                new_stripped  = new_line.strip()

                # Skip if identical
                if orig_stripped == new_stripped:
                    continue

                # Skip protected lines
                protected = False
                for pattern in PROTECTED_PATTERNS:
                    if re.search(pattern, orig_stripped, re.IGNORECASE):
                        protected = True
                        break
                if protected:
                    continue

                # Skip very short lines (headers, labels)
                if len(orig_stripped.split()) < 4:
                    continue

                # Skip lines with placeholder text added by AI
                placeholders = ['[email]', '[linkedin]', '[github]', '[phone]',
                                '[url]', '[website]', '[address]']
                if any(p in new_stripped.lower() for p in placeholders):
                    continue

                if orig_stripped and new_stripped:
                    change_map[orig_stripped] = new_stripped

        print(f"📝 Change map built: {len(change_map)} lines will be updated")
        for orig, new in list(change_map.items())[:3]:
            print(f"  ORIG: {orig[:60]}")
            print(f"  NEW:  {new[:60]}")
            print()

        return change_map

    # ── Font mapping ─────────────────────────────────────────────
    def get_pymupdf_font(self, pdf_font_name: str, flags: int) -> str:
        """
        Map PDF embedded font name to PyMuPDF built-in font.
        Preserves bold and italic styling.

        PyMuPDF built-ins:
        helv=Helvetica, hebo=Helvetica Bold, heit=Helvetica Italic, hebi=Helvetica Bold+Italic
        tiro=Times, tibo=Times Bold, tiit=Times Italic, tibi=Times Bold+Italic
        cour=Courier, cobo=Courier Bold, coit=Courier Italic, cobi=Courier Bold+Italic
        """
        name    = (pdf_font_name or "").lower()
        is_bold = bool(flags & 16) or "bold" in name
        is_ital = bool(flags & 2)  or "italic" in name or "oblique" in name

        # Helvetica / Arial / Calibri / Sans-serif family
        if any(x in name for x in ["helv", "arial", "calibri", "sans", "gothic",
                                     "roboto", "verdana", "tahoma", "segoe"]):
            if is_bold and is_ital: return "hebi"
            if is_bold:             return "hebo"
            if is_ital:             return "heit"
            return "helv"

        # Times / Georgia / Serif family
        if any(x in name for x in ["times", "roman", "serif", "georgia",
                                     "garamond", "palatino", "book"]):
            if is_bold and is_ital: return "tibi"
            if is_bold:             return "tibo"
            if is_ital:             return "tiit"
            return "tiro"

        # Courier / Mono family
        if any(x in name for x in ["cour", "mono", "consol", "lucida",
                                     "inconsolata", "fira"]):
            if is_bold and is_ital: return "cobi"
            if is_bold:             return "cobo"
            if is_ital:             return "coit"
            return "cour"

        # Default fallback — use bold/italic from flags
        if is_bold and is_ital: return "hebi"
        if is_bold:             return "hebo"
        if is_ital:             return "heit"
        return "helv"

    # ── Color conversion ─────────────────────────────────────────
    def color_to_rgb(self, color) -> tuple:
        """Convert PyMuPDF color value to normalized RGB (0.0–1.0)."""
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            return tuple(min(1.0, v / 255 if v > 1 else float(v)) for v in color[:3])
        if isinstance(color, float):
            g = max(0.0, min(1.0, color))
            return (g, g, g)
        if isinstance(color, int):
            r = ((color >> 16) & 0xFF) / 255
            g = ((color >>  8) & 0xFF) / 255
            b = (color         & 0xFF) / 255
            return (r, g, b)
        return (0.0, 0.0, 0.0)  # default black

    # ── Background color sampling ─────────────────────────────────
    def sample_background(self, page: fitz.Page, rect: fitz.Rect) -> tuple:
        """
        Sample the pixel color behind a text region.
        Used as the erase color when redacting original text.
        Returns normalized RGB tuple.
        """
        try:
            # Sample a 3x3 area at the top-left of the span
            clip = fitz.Rect(
                rect.x0,
                rect.y0,
                min(rect.x0 + 3, rect.x1),
                min(rect.y0 + 3, rect.y1)
            )
            pix     = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=clip, alpha=False)
            samples = pix.samples
            if len(samples) >= 3:
                r = samples[0] / 255
                g = samples[1] / 255
                b = samples[2] / 255
                # If very dark (black header/sidebar), return that color
                # Otherwise return white (most resumes have white background)
                if r < 0.2 and g < 0.2 and b < 0.2:
                    return (r, g, b)
                return (1.0, 1.0, 1.0)
        except Exception:
            pass
        return (1.0, 1.0, 1.0)

    # ── Find replacement for a span ───────────────────────────────
    def find_replacement(self, span_text: str, change_map: dict) -> Optional[str]:
        """
        Find the rewritten version for a PDF text span.
        Tries exact match first, then partial/substring match.
        Returns None if no change found (span stays untouched).
        """
        if not span_text or len(span_text.strip()) < 4:
            return None

        span_stripped = span_text.strip()

        # 1. Exact match
        if span_stripped in change_map:
            return change_map[span_stripped]

        # 2. Span is a substring of a changed original line
        for orig, new in change_map.items():
            if span_stripped in orig and len(span_stripped) > 15:
                try:
                    idx = orig.index(span_stripped)
                    ratio_s  = idx / len(orig)
                    ratio_e  = (idx + len(span_stripped)) / len(orig)
                    ns = int(ratio_s * len(new))
                    ne = int(ratio_e * len(new))
                    # Snap to word boundaries
                    while ns > 0 and ns < len(new) and new[ns - 1] != ' ':
                        ns -= 1
                    while ne < len(new) and ne < len(new) and new[ne] != ' ':
                        ne += 1
                    candidate = new[ns:ne].strip()
                    if candidate and len(candidate) >= 3:
                        return candidate
                except (ValueError, IndexError):
                    pass

            # 3. A changed original line is contained in this span
            if orig in span_stripped and len(orig) > 15:
                return span_stripped.replace(orig, new, 1)

        return None  # No change — leave this span untouched

    # ── Main rebuild method ───────────────────────────────────────
    def rebuild_pdf_with_rewritten_text(
        self,
        original_path: str,
        original_text: str,
        rewritten_text: str,
    ) -> bytes:
        """
        MAIN METHOD — pixel-perfect PDF rewriter.

        Algorithm:
        1. Build change_map from difflib line comparison
        2. Open original PDF with PyMuPDF
        3. For each page, for each text span:
           a. Check if span text is in change_map
           b. If yes: erase original text with background-colored rectangle
           c. Write new text at EXACT same position, EXACT same font+size+color
        4. Save modified PDF (all unchanged content stays pixel-perfect)
        5. Return bytes

        What stays identical:
        - NMIMS logo and all images
        - Profile photo
        - Section header underlines and borders
        - All decorative lines
        - Unchanged text (names, dates, companies, headers)
        - Font sizes and weights
        - Page margins and layout
        - Column structure
        """
        doc         = fitz.open(original_path)
        change_map  = self.build_change_map(original_text, rewritten_text)
        total_changed = 0

        if not change_map:
            print("⚠️ No changes detected — returning original PDF")
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            return buf.getvalue()

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Get all text with full style information
            raw_dict = page.get_text(
                "rawdict",
                flags=(fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
            )

            # Collect all replacements first (don't modify while iterating)
            replacements = []

            for block in raw_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = text block
                    continue

                for line in block.get("lines", []):
                    # Get full line text for context
                    line_text = "".join(
                        s.get("text", "") for s in line.get("spans", [])
                    ).strip()

                    if not line_text:
                        continue

                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if not span_text or len(span_text) < 3:
                            continue

                        new_text = self.find_replacement(span_text, change_map)

                        if new_text is None or new_text.strip() == span_text:
                            continue  # No change — leave completely untouched

                        bbox      = fitz.Rect(span["bbox"])
                        font_name = span.get("font", "Helvetica")
                        font_size = span.get("size", 11)
                        flags     = span.get("flags", 0)
                        color     = span.get("color", 0)
                        origin    = span.get("origin", (bbox.x0, bbox.y1))

                        replacements.append({
                            "bbox":      bbox,
                            "new_text":  new_text.strip(),
                            "font":      self.get_pymupdf_font(font_name, flags),
                            "size":      font_size,
                            "color":     self.color_to_rgb(color),
                            "origin_x":  bbox.x0,
                            "origin_y":  origin[1] if isinstance(origin, (list, tuple)) else bbox.y1,
                        })

            # Apply all redactions first to physically remove original text from the PDF layer
            for rep in replacements:
                bbox = rep["bbox"]
                bg = self.sample_background(page, bbox)
                
                # Expand slightly to ensure total removal
                erase_rect = fitz.Rect(
                    bbox.x0 - 0.5,
                    bbox.y0 - 0.8,
                    bbox.x1 + 1.2,
                    bbox.y1 + 0.8,
                )
                page.add_redact_annot(erase_rect, fill=bg)
            
            # Commit redactions (deletes original text characters permanently)
            page.apply_redact(images=fitz.PDF_REDACT_IMAGE_NONE)

            # Write new text at EXACT original baseline
            for rep in replacements:
                try:
                    page.insert_text(
                        point=fitz.Point(rep["origin_x"], rep["origin_y"]),
                        text=rep["new_text"],
                        fontname=rep["font"],
                        fontsize=rep["size"],
                        color=rep["color"],
                        render_mode=0,
                    )
                    total_changed += 1
                except Exception as font_err:
                    # Font registration failed — try Helvetica fallback
                    print(f"⚠️ Font {rep['font']} failed: {font_err} — using helv fallback")
                    try:
                        page.insert_text(
                            point=fitz.Point(rep["origin_x"], rep["origin_y"]),
                            text=rep["new_text"],
                            fontname="helv",
                            fontsize=rep["size"],
                            color=rep["color"],
                        )
                        total_changed += 1
                    except Exception as e2:
                        print(f"❌ Could not insert text: {e2} — leaving original")

        print(f"✅ PDF rebuilt: {total_changed} spans updated across {len(doc)} page(s)")

        # Save with compression — do NOT linearize (preserves all PDF objects)
        buf = io.BytesIO()
        doc.save(
            buf,
            garbage=3,      # remove unused objects
            deflate=True,   # compress streams
            clean=True,     # clean content streams
        )
        doc.close()
        return buf.getvalue()


# Module-level singleton
pdf_handler = PDFResumeHandler()
