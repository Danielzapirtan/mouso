#!/usr/bin/env python3
"""
mausolee_pdf.py

Aplicație CLI care preia text + fotografii despre cinci mausolee din lume
(Wikipedia + Wikimedia Commons) și scrie un PDF de ~4 pagini, în limba română.

Mausolee (în ordine):
  1. Mausoleul Primului Împărat Qin (China)
  2. Taj Mahal (India)
  3. Mausoleul Mărășești (România)
  4. Mormântul lui Napoleon (Les Invalides, Franța)
  5. Mausoleul lui Lenin (Rusia)

Dependențe:
    pip install reportlab wikipedia-api requests pillow

Utilizare:
    python mausolee_pdf.py --output mausolee.pdf
"""

import argparse
import sys
import os
import time
from io import BytesIO

# ---------------------------------------------------------------------------
# Forțează UTF-8 la stdout/stderr ÎNAINTE de orice print(),
# ca diacriticele românești să nu mai provoace UnicodeEncodeError
# pe Windows (cp1252) sau în alte medii cu encoding implicit restrictiv.
# ---------------------------------------------------------------------------
def _force_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        # Fallback pentru Python < 3.7 sau stream-uri fără reconfigure()
        elif hasattr(stream, "buffer"):
            try:
                import io
                wrapped = io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace",
                    line_buffering=True,
                )
                setattr(sys, stream_name, wrapped)
            except Exception:
                pass


_force_utf8_stdio()

import requests

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.lib.colors import HexColor, grey
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
        PageBreak, KeepTogether, NextPageTemplate, Image,
    )
    from PIL import Image as PILImage
except ImportError as e:
    print(f"EROARE: lipsește o dependență ({e}). "
          "Instalează cu: pip install reportlab wikipedia-api requests pillow")
    sys.exit(1)

try:
    import wikipediaapi
except ImportError:
    print("EROARE: wikipedia-api este necesar. "
          "Instalează cu: pip install wikipedia-api")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configurație: cele cinci mausolee (text în română)
# ---------------------------------------------------------------------------
MAUSOLEUMS = [
    {
        "title": "Mausoleul Primului Împărat Qin",
        "subtitle": "Lintong, Shaanxi, China",
        "wiki_title": "Mausoleul Împăratului Qin Shi Huang",
        "commons_search": "Qin Shi Huang Mausoleum",
        "fallback_text": (
            "Mausoleul Primului Împărat Qin, situat lângă Xi'an, în provincia "
            "Shaanxi din China, a fost construit între 246 î.Hr. și 208 î.Hr. "
            "pentru Qin Shi Huang, primul împărat al Chinei unificate. Situl "
            "acoperă 56,25 kilometri pătrați și include un tumul funerar înalt "
            "de 76 de metri. Este celebru pentru Armata de Teracotă – mii de "
            "soldați, care și cai de dimensiuni naturale, îngropați în gropi "
            "pentru a-l păzi pe împărat în viața de apoi. Descoperit în 1974 de "
            "țărani care săpau o fântână, situl a fost declarat Patrimoniu "
            "Mondial UNESCO în 1987. Camera funerară centrală rămâne "
            "neexcavată, iar izvoarele istorice sugerează că adăpostește râuri "
            "de mercur și arbalete automate."
        ),
    },
    {
        "title": "Taj Mahal",
        "subtitle": "Agra, Uttar Pradesh, India",
        "wiki_title": "Taj Mahal",
        "fallback_text": (
            "Taj Mahal este un mausoleu de marmură albă-ivorie situat pe malul "
            "sudic al fluviului Yamuna, în Agra, India. A fost comandat în 1631 "
            "de împăratul mogul Shah Jahan pentru a adăposti mormântul soției "
            "sale preferate, Mumtaz Mahal. Construcția a durat aproximativ 20 "
            "de ani (1632–1648) și a implicat mii de artizani și meșteșugari. "
            "Complexul cuprinde o poartă principală, o grădină formală, o "
            "moschee și o casă pentru oaspeți. Mormântul este piesa centrală a "
            "întregului ansamblu. Taj Mahal este considerat cel mai frumos "
            "exemplu al arhitecturii mogule, îmbinând stiluri persane, indiene "
            "și islamice. A devenit Patrimoniu Mondial UNESCO în 1983 și este "
            "privit în general ca una dintre capodoperele universale ale "
            "patrimoniului mondial."
        ),
    },
    {
        "title": "Mausoleul Mărășești",
        "subtitle": "Județul Vrancea, România",
        "wiki_title": "Mausoleul de la Mărășești",
        "fallback_text": (
            "Mausoleul de la Mărășești comemorează soldații căzuți în Bătălia de "
            "la Mărășești din Primul Război Mondial (1917). Construit între 1923 "
            "și 1938 după planurile arhitecților George Cristinel și Constantin "
            "Pomponiu, monumentul a fost inaugurat la 18 septembrie 1938. Este "
            "cel mai mare mausoleu din România și printre cele mai impunătoare "
            "din Europa. Construcția circulară are 30 de metri înălțime și 40 de "
            "metri în diametru, fiind realizată din beton armat placat cu blocuri "
            "de andezit de Deva. Criptele de la nivelul solului adăpostesc "
            "rămășițele a aproximativ 6.000 de soldați și ofițeri români. În "
            "centru se află sarcofagul generalului Eremia Grigorescu. Nivelul "
            "superior găzduiește o rotondă în care sunt expuse steagurile "
            "unităților care au luptat în acea bătălie."
        ),
    },
    {
        "title": "Mormântul lui Napoleon",
        "subtitle": "Les Invalides, Paris, Franța",
        "wiki_title": "Les Invalides",
        "fallback_text": (
            "Mormântul lui Napoleon se află sub Cupola aurită de la Les Invalides, "
            "în Paris, Franța. Domul (Dôme des Invalides) a fost construit inițial "
            "ca o capelă regală de arhitectul Jules Hardouin-Mansart, sub Ludovic "
            "al XIV-lea, începând cu 1677, și a fost cea mai înaltă clădire din "
            "Paris până la Turnul Eiffel. Napoleon Bonaparte a murit în exil pe "
            "insula Sfânta Elena în 1821. În 1840, regele Ludovic-Filip a ordonat "
            "repatrierea rămășițelor sale în Franța, iar arhitectul Visconti a "
            "efectuat lucrări ample de excavare pentru a amenaja mormântul "
            "imperial sub Cupolă. Trupul lui Napoleon a fost depus acolo la 2 "
            "aprilie 1861. Sub Cupolă se află și mormintele lui Napoleon al II-lea, "
            "ale lui Joseph și Jérôme Bonaparte, precum și cele ale mareșalilor "
            "Foch și Lyautey."
        ),
    },
    {
        "title": "Mausoleul lui Lenin",
        "subtitle": "Piața Roșie, Moscova, Rusia",
        "wiki_title": "Mausoleul lui Lenin",
        "fallback_text": (
            "Mausoleul lui Lenin din Piața Roșie din Moscova este locul de veci al "
            "lui Vladimir Lenin, fondatorul statului sovietic. Lenin a murit la "
            "21 ianuarie 1924, la vârsta de 53 de ani. În câteva zile a fost "
            "ridicată o criptă provizorie din lemn, iar primul mausoleu permanent "
            "a fost deschis publicului la 1 august 1924. Actuala construcție din "
            "piatră, proiectată de arhitectul Alexei Șciusev și realizată din "
            "granit roșu și negru pe o structură din beton armat, a fost "
            "finalizată în octombrie 1930. Are 12 metri înălțime și un volum de "
            "5.800 de metri cubi. Trupul îmbălsămat al lui Lenin se află într-un "
            "sarcofag de cristal proiectat de Konstantin Melnikov. Mausoleul "
            "rămâne un obiectiv turistic major, cu aproximativ 450.000 de "
            "vizitatori pe an."
        ),
    },
]


# ---------------------------------------------------------------------------
# Preluare text din Wikipedia
# ---------------------------------------------------------------------------
def fetch_wikipedia_summary(wiki_title: str, language: str = "ro") -> str | None:
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="GeneratorMausoleePDF/1.0 (educational project)",
            language=language,
        )
        page = wiki.page(wiki_title)
        if page.exists() and page.summary:
            summary = page.summary.strip()
            if len(summary) > 3000:
                summary = summary[:3000].rsplit(".", 1)[0] + "."
            return summary
    except Exception as exc:
        print(f"  [avertisment] preluarea textului Wikipedia a eșuat "
              f"pentru '{wiki_title}': {exc}")
    return None


# ---------------------------------------------------------------------------
# Preluare imagine din Wikimedia Commons (API MediaWiki, fără cheie)
# ---------------------------------------------------------------------------
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "GeneratorMausoleePDF/1.0 (educational project)"}


def _commons_thumb_for_file(filename: str, width: int = 800) -> str | None:
    params = {
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": width,
        "format": "json",
    }
    try:
        r = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for _, page in pages.items():
            info = page.get("imageinfo", [])
            if info:
                return info[0].get("thumburl") or info[0].get("url")
    except Exception as exc:
        print(f"  [avertisment] căutarea fișierului pe Commons a eșuat: {exc}")
    return None


def fetch_lead_image_url(wiki_title: str, language: str = "ro") -> str | None:
    api = f"https://{language}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": wiki_title,
        "prop": "pageimages",
        "piprop": "name|original",
        "pithumbsize": 800,
        "format": "json",
        "redirects": 1,
    }
    try:
        r = requests.get(api, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for _, page in pages.items():
            name = page.get("pageimage")
            if name:
                thumb = _commons_thumb_for_file(name, width=800)
                if thumb:
                    return thumb
            original = page.get("original", {}).get("source")
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
            if original:
                return original
    except Exception as exc:
        print(f"  [avertisment] căutarea imaginii Wikipedia a eșuat "
              f"pentru '{wiki_title}': {exc}")
    return None


def search_commons_image_url(query: str, width: int = 800) -> str | None:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": 1,
        "format": "json",
    }
    try:
        r = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        results = r.json().get("query", {}).get("search", [])
        if results:
            filename = results[0].get("title", "").removeprefix("File:")
            if filename:
                return _commons_thumb_for_file(filename, width)
    except Exception as exc:
        print(f"  [avertisment] căutarea imaginii pe Commons a eșuat "
              f"pentru '{query}': {exc}")
    return None


def download_image(url: str, max_bytes: int = 12 * 1024 * 1024):
    last_exc = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
            if r.status_code == 429:
                raise requests.HTTPError(f"429 Client Error: Too Many Requests for {url}")
            r.raise_for_status()
            buf = BytesIO()
            total = 0
            for chunk in r.iter_content(8192):
                total += len(chunk)
                if total > max_bytes:
                    print("  [avertisment] imaginea este prea mare, se sare peste")
                    return None
                buf.write(chunk)
            buf.seek(0)
            img = PILImage.open(buf)
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            return img
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            print(f"  [avertisment] descărcarea imaginii a eșuat: {exc}")
    return None


def make_reportlab_image(pil_img, max_w_cm: float, max_h_cm: float) -> Image:
    w_px, h_px = pil_img.size
    aspect = h_px / w_px
    max_w = max_w_cm * cm
    max_h = max_h_cm * cm
    draw_w = max_w
    draw_h = draw_w * aspect
    if draw_h > max_h:
        draw_h = max_h
        draw_w = draw_h / aspect
    buf = BytesIO()
    pil_img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return Image(buf, width=draw_w, height=draw_h)


# ---------------------------------------------------------------------------
# Generare PDF
# ---------------------------------------------------------------------------
class MausoleumPDF(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)


def build_pdf(output_path: str, language: str = "ro") -> None:
    print("Se preiau datele de pe internet ...")
    entries = []
    for m in MAUSOLEUMS:
        print(f"  {m['title']}:")
        text = fetch_wikipedia_summary(m["wiki_title"], language)
        if not text or len(text) < 100:
            text = m["fallback_text"]
            print("    text: text de rezervă")
        else:
            print(f"    text: Wikipedia ({len(text)} caractere)")

        img_url = fetch_lead_image_url(m["wiki_title"], language)
        if not img_url and m.get("commons_search"):
            img_url = search_commons_image_url(m["commons_search"])
        img = None
        if img_url:
            time.sleep(1)
            img = download_image(img_url)
        if img is not None:
            print(f"    imagine: OK ({img.size[0]}x{img.size[1]} px)")
        else:
            print("    imagine: indisponibilă")

        entries.append({**m, "body": text, "image": img})

    font_sets = (
        (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
         ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")),
        ("/usr/share/fonts/truetype/dejavu",
         ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
          "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf")),
        ("/usr/share/fonts/truetype/liberation2",
         ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
          "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf")),
        ("/Library/Fonts",
         ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf",
          "Arial Bold Italic.ttf")),
        ("/System/Library/Fonts/Supplemental",
         ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf",
          "Arial Bold Italic.ttf")),
    )
    font_paths = next(
        ([os.path.join(font_dir, name) for name in filenames]
         for font_dir, filenames in font_sets
         if all(os.path.isfile(os.path.join(font_dir, name))
                for name in filenames)),
        None,
    )
    if font_paths is None:
        raise RuntimeError(
            "Nu a fost găsit un font TrueType cu suport pentru diacritice "
            "românești (Arial, DejaVu Sans sau Liberation Sans).")
    for font_name, font_path in zip(
            ("MausoleeSans", "MausoleeSans-Bold", "MausoleeSans-Italic",
             "MausoleeSans-BoldItalic"), font_paths):
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, font_path))

    # ---- Stiluri --------------------------------------------------------
    styles = getSampleStyleSheet()
    cover_title = ParagraphStyle(
        "CoverTitle", parent=styles["Title"], fontName="MausoleeSans-Bold",
        fontSize=28, leading=34, alignment=TA_CENTER,
        textColor=HexColor("#f0f0f0"),
    )
    cover_sub = ParagraphStyle(
        "CoverSub", parent=styles["Normal"], fontName="MausoleeSans",
        fontSize=13, leading=17, alignment=TA_CENTER,
        textColor=HexColor("#b0b0d0"),
    )
    h_style = ParagraphStyle(
        "H1", parent=styles["Heading1"], fontName="MausoleeSans-Bold",
        fontSize=17, leading=21, spaceAfter=2,
        textColor=HexColor("#16213e"),
    )
    loc_style = ParagraphStyle(
        "Loc", parent=styles["Normal"], fontName="MausoleeSans-Italic",
        fontSize=10, leading=13, spaceAfter=6, textColor=grey,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="MausoleeSans",
        fontSize=10.2, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6,
    )
    caption_style = ParagraphStyle(
        "Caption", parent=styles["Normal"], fontName="MausoleeSans-Italic",
        fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=grey,
        spaceBefore=2, spaceAfter=6,
    )

    def cover_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor("#16213e"))
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    def content_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grey)
        canvas.drawString(2 * cm, 1.2 * cm, "Cinci mausolee ale lumii")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Pagina {doc.page}")
        canvas.restoreState()

    # ---- Conținut -------------------------------------------------------
    story = [NextPageTemplate("Content")]

    # Copertă
    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph("Cinci mausolee<br/>ale lumii", cover_title))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "Qin · Taj Mahal · Mărășești · Napoleon · Lenin", cover_sub))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "O scurtă prezentare ilustrată a cinci morminte monumentale<br/>"
        "din China, India, România, Franța și Rusia",
        cover_sub,
    ))
    story.append(PageBreak())

    for idx, e in enumerate(entries):
        block = [Paragraph(e["title"], h_style),
                 Paragraph(e["subtitle"], loc_style)]

        if e["image"] is not None:
            img_flow = make_reportlab_image(e["image"], max_w_cm=15.5, max_h_cm=9.5)
            block.append(img_flow)
            block.append(Paragraph("Fotografie: Wikimedia Commons", caption_style))

        for para in [p.strip() for p in e["body"].split("\n") if p.strip()]:
            safe = (para.replace("&", "&amp;")
                         .replace("<", "&lt;")
                         .replace(">", "&gt;"))
            block.append(Paragraph(safe, body_style))

        story.append(KeepTogether(block))
        if idx < len(entries) - 1:
            story.append(PageBreak())

    # ---- Construire -----------------------------------------------------
    doc = MausoleumPDF(
        output_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title="Cinci mausolee ale lumii",
        author="Generator de PDF cu mausolee",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="normal")
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[frame], onPage=cover_page),
        PageTemplate(id="Content", frames=[frame], onPage=content_page),
    ])
    doc.build(story)

    print(f"\nPDF scris în: {output_path}")


def main():
    # Cei care redirecționează stdout pe Windows primesc în continuare
    # UTF-8 datorită _force_utf8_stdio() de la început.
    p = argparse.ArgumentParser(
        description="Generează un PDF (cu fotografii) despre cinci mausolee "
                    "ale lumii, în limba română.")
    p.add_argument("-o", "--output", default="mausolee.pdf",
                   help="calea fișierului PDF de ieșire (implicit: mausolee.pdf)")
    p.add_argument("-l", "--language", default="ro",
                   help="codul de limbă Wikipedia pentru preluarea datelor "
                        "(implicit: ro)")
    args = p.parse_args()
    try:
        build_pdf(args.output, args.language)
    except Exception as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
