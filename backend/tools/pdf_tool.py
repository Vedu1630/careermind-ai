import fitz  # pymupdf
import io
import os
import difflib
import tempfile
from PIL import Image, ImageDraw, ImageFont
from typing import Optional

DPI = 150  # Render resolution — 150 DPI balances quality and speed

class PDFResumeHandler:

    def extract_text_for_ai(self, file_path: str) -> str:
        """
        Extract plain text from PDF preserving reading order.
        Used to send to Gemini for rewriting.
        """
        pages_text = []
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text = page.get_text("text")
                if text:
                    pages_text.append(text)
            doc.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("PyMuPDF text extraction failed: %s", e)
        return "\n\n".join(pages_text)

    def extract_text_blocks_with_positions(self, file_path: str) -> list:
        """
        Extract text blocks with their PIXEL coordinates at target DPI.
        Returns list of dicts: {text, x0, y0, x1, y1, page_num, fontsize, bold}
        Coordinates are in pixels at DPI=150.
        """
        scale = DPI / 72.0  # PDF points to pixels
        all_blocks = []

        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc):
            raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text or len(text) < 2:
                            continue
                        bbox = span["bbox"]
                        flags = span.get("flags", 0)
                        all_blocks.append({
                            "text": text,
                            "x0": bbox[0] * scale,
                            "y0": bbox[1] * scale,
                            "x1": bbox[2] * scale,
                            "y1": bbox[3] * scale,
                            "pdf_x0": bbox[0],
                            "pdf_y0": bbox[1],
                            "pdf_x1": bbox[2],
                            "pdf_y1": bbox[3],
                            "page_num": page_num,
                            "fontsize": span.get("size", 11) * scale / 72 * 72,
                            "bold": bool(flags & 16),
                            "italic": bool(flags & 2),
                            "color": span.get("color", 0),
                            "font": span.get("font", "Helvetica"),
                            "origin_fontsize": span.get("size", 11),
                        })
        doc.close()
        return all_blocks

    def render_page_to_image(self, file_path: str, page_num: int = 0) -> Image.Image:
        """
        Render a PDF page to a PIL Image at target DPI.
        This captures the COMPLETE visual appearance — logo, photo, lines, borders, everything.
        """
        doc = fitz.open(file_path)
        page = doc[page_num]
        mat = fitz.Matrix(DPI / 72, DPI / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        return img

    def build_change_map(self, original_text: str, rewritten_text: str) -> dict:
        """
        Build a word-level and line-level change map.
        Returns dict mapping original_line_text -> rewritten_line_text
        ONLY for lines that actually changed.
        """
        orig_lines = [l.strip() for l in original_text.split('\n') if l.strip()]
        new_lines  = [l.strip() for l in rewritten_text.split('\n') if l.strip()]

        change_map = {}
        matcher = difflib.SequenceMatcher(None, orig_lines, new_lines)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                # Map each changed original line to its rewritten version
                orig_chunk = orig_lines[i1:i2]
                new_chunk  = new_lines[j1:j2]
                for k, orig_line in enumerate(orig_chunk):
                    if k < len(new_chunk):
                        if orig_line != new_chunk[k]:
                            change_map[orig_line] = new_chunk[k]
            # 'equal' and 'delete' lines are NOT in the map — they stay untouched

        return change_map

    def find_replacement_for_span(self, span_text: str, change_map: dict) -> Optional[str]:
        """
        Find the rewritten version of a PDF text span.
        Tries exact match, then substring match with proportional replacement.
        Returns None if no change found (span should be left untouched).
        """
        span_stripped = span_text.strip()

        # 1. Exact match
        if span_stripped in change_map:
            return change_map[span_stripped]

        # 2. The span IS a substring of a changed line
        for orig, new in change_map.items():
            if span_stripped in orig and len(span_stripped) > 12:
                # Find position of span in original line
                idx = orig.index(span_stripped)
                ratio_start = idx / len(orig)
                ratio_end = (idx + len(span_stripped)) / len(orig)
                # Extract proportional slice from new line
                s = int(ratio_start * len(new))
                e = int(ratio_end * len(new))
                # Snap to word boundaries
                while s > 0 and new[s-1] != ' ':
                    s -= 1
                while e < len(new) and new[e] != ' ':
                    e += 1
                candidate = new[s:e].strip()
                if candidate:
                    return candidate

            # 3. A changed line is a substring of this span
            if orig in span_stripped and len(orig) > 12:
                return span_stripped.replace(orig, new)

        return None  # No change — leave span untouched

    def get_font_for_span(self, bold: bool, italic: bool, fontsize_px: float):
        """
        Get a PIL ImageFont for drawing text.
        Uses system fonts that closely match typical resume fonts (Calibri/Arial/Helvetica).
        Falls back gracefully to PIL default.
        """
        # Try to find system fonts in order of preference
        font_candidates = {
            (True, True):   [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "arialbi.ttf",
            ],
            (True, False):  [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "arialbd.ttf",
            ],
            (False, True):  [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
                "ariali.ttf",
            ],
            (False, False): [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "arial.ttf",
            ],
        }

        size = max(8, int(fontsize_px))
        candidates = font_candidates.get((bold, italic), font_candidates[(False, False)])

        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue

        # Final fallback — PIL built-in bitmap font (no size control)
        return ImageFont.load_default()

    def get_text_color_rgb(self, color_int) -> tuple:
        """Convert PyMuPDF color integer to PIL RGB tuple (0-255)."""
        if isinstance(color_int, (list, tuple)) and len(color_int) >= 3:
            return tuple(int(c * 255) if c <= 1 else int(c) for c in color_int[:3])
        if isinstance(color_int, float):
            v = int(color_int * 255)
            return (v, v, v)
        if isinstance(color_int, int):
            r = (color_int >> 16) & 0xFF
            g = (color_int >> 8) & 0xFF
            b = color_int & 0xFF
            return (r, g, b)
        return (0, 0, 0)

    def _normalize_color(self, color_int: int) -> tuple:
        """Convert PyMuPDF integer color to RGB tuple 0-1."""
        if isinstance(color_int, (list, tuple)):
            return tuple(c / 255 if c > 1 else c for c in color_int[:3])
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        return (r / 255, g / 255, b / 255)

    def _map_font(self, pdf_font_name: str) -> str:
        """Map PDF embedded font names to PyMuPDF standard font names to preserve style."""
        name = pdf_font_name.lower()
        is_bold = "bold" in name or "black" in name or "heavy" in name
        is_italic = "italic" in name or "oblique" in name
        
        if "times" in name or "serif" in name or "roman" in name:
            if is_bold and is_italic:
                return "tibi"
            elif is_bold:
                return "tibo"
            elif is_italic:
                return "tiit"
            return "times"
        elif "courier" in name or "mono" in name or "consolas" in name:
            if is_bold and is_italic:
                return "cobi"
            elif is_bold:
                return "cobo"
            elif is_italic:
                return "coit"
            return "cour"
        else: # Default to Helvetica/Arial sans-serif
            if is_bold and is_italic:
                return "hebi"
            elif is_bold:
                return "hebo"
            elif is_italic:
                return "heit"
            return "helv"

    def rebuild_pdf_with_rewritten_text(
        self,
        original_path: str,
        original_text: str,
        rewritten_text: str,
    ) -> bytes:
        """
        Main method. Pixel-perfect resume rewriter.

        Process:
        1. Render original PDF page to PNG image (preserves everything visually)
        2. Build change_map from difflib line comparison
        3. For each text span that changed:
           a. White-box erase the original text at its pixel coordinates
           b. Draw new text at the exact same position with matching style
        4. Convert modified image back to PDF
        5. Composite a digital invisible text layer (render_mode=3) for ALL text
           (both unchanged and rewritten) at exact PDF coordinates to make the PDF
           fully searchable, selectable, and parsable by resume analyzers.
        6. Return PDF bytes
        """
        doc_orig = fitz.open(original_path)
        num_pages = len(doc_orig)
        doc_orig.close()

        all_spans = self.extract_text_blocks_with_positions(original_path)
        change_map = self.build_change_map(original_text, rewritten_text)

        output_images = []

        for page_num in range(num_pages):
            # Render original page to image — this is our canvas
            img = self.render_page_to_image(original_path, page_num)
            draw = ImageDraw.Draw(img)

            page_spans = [s for s in all_spans if s["page_num"] == page_num]

            for span in page_spans:
                new_text = self.find_replacement_for_span(span["text"], change_map)

                if new_text is None:
                    continue  # No change — leave pixel untouched

                x0, y0, x1, y1 = span["x0"], span["y0"], span["x1"], span["y1"]

                # Sample the background color at this exact pixel region
                # by looking at a 2x2 area just outside the text baseline
                try:
                    sample_x = int(max(0, x0))
                    sample_y = int(max(0, y0))
                    sample_region = img.crop((sample_x, sample_y, sample_x + 4, sample_y + 4))
                    pixels = list(sample_region.getdata())
                    # Average the sampled pixels for background color
                    bg_r = int(sum(p[0] for p in pixels) / len(pixels))
                    bg_g = int(sum(p[1] for p in pixels) / len(pixels))
                    bg_b = int(sum(p[2] for p in pixels) / len(pixels))
                    # If background is very dark (under dark header), use it
                    # If bright, use white
                    if bg_r > 200 and bg_g > 200 and bg_b > 200:
                        bg_color = (255, 255, 255)
                    else:
                        bg_color = (bg_r, bg_g, bg_b)
                except Exception:
                    bg_color = (255, 255, 255)

                # Step 1: Erase original text with background rectangle
                # Add small padding to ensure full coverage
                erase_box = [
                    max(0, x0 - 1),
                    max(0, y0 - 1),
                    min(img.width, x1 + 2),
                    min(img.height, y1 + 2),
                ]
                draw.rectangle(erase_box, fill=bg_color)

                # Step 2: Draw new text at same position with matching style
                fontsize_px = (y1 - y0) * 0.85  # Height of bbox as approx font size
                font = self.get_font_for_span(span["bold"], span["italic"], fontsize_px)
                text_color = self.get_text_color_rgb(span["color"])

                # Draw text at the top-left of the original bounding box
                try:
                    draw.text(
                        (x0, y0),
                        new_text,
                        font=font,
                        fill=text_color,
                    )
                except Exception:
                    # Fallback: draw with default font
                    draw.text((x0, y0), new_text, fill=text_color)

            output_images.append(img)

        # Convert images back to PDF and overlay invisible text layer for searchability/parsing
        writer = fitz.open()
        
        for page_num in range(num_pages):
            img = output_images[page_num]
            buf = io.BytesIO()
            img.save(buf, format="PDF", resolution=DPI)
            page_pdf_bytes = buf.getvalue()
            
            # Open this single-page PDF to inject the digital text layer
            tmp_doc = fitz.open("pdf", page_pdf_bytes)
            page = tmp_doc[0]
            
            # Inject invisible digital text for all spans on this page
            page_spans = [s for s in all_spans if s["page_num"] == page_num]
            
            for span in page_spans:
                new_text = self.find_replacement_for_span(span["text"], change_map)
                text_to_write = new_text if new_text is not None else span["text"]
                
                # Align text baseline (typically 80% of bbox height)
                baseline_y = span["pdf_y0"] + (span["pdf_y1"] - span["pdf_y0"]) * 0.8
                
                try:
                    page.insert_text(
                        point=fitz.Point(span["pdf_x0"], baseline_y),
                        text=text_to_write,
                        fontsize=span["origin_fontsize"],
                        fontname=self._map_font(span["font"]),
                        render_mode=3  # Render Mode 3: Invisible text (neither fill nor stroke)
                    )
                except Exception:
                    # Fallback standard Helvetica
                    try:
                        page.insert_text(
                            point=fitz.Point(span["pdf_x0"], baseline_y),
                            text=text_to_write,
                            fontsize=span["origin_fontsize"],
                            fontname="helv",
                            render_mode=3
                        )
                    except Exception:
                        pass
            
            # Commit the text changes by saving to bytes first
            commit_buf = io.BytesIO()
            tmp_doc.save(commit_buf)
            tmp_doc.close()
            
            # Open and insert the committed single-page PDF
            committed_doc = fitz.open("pdf", commit_buf.getvalue())
            writer.insert_pdf(committed_doc)
            committed_doc.close()

        out_buf = io.BytesIO()
        writer.save(out_buf)
        writer.close()
        return out_buf.getvalue()


pdf_handler = PDFResumeHandler()
