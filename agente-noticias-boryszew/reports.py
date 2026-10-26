from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

LIMITATION = ('Informe basado en titulares y extractos públicos indexados, no en la lectura íntegra de los artículos. '
              'La cobertura de LinkedIn se limita a resultados públicos indexados y puede ser nula. '
              'Los enlaces de Google News pueden redirigir al medio original. No se incluyen publicaciones sin fecha verificable.')


def build_pdf(report):
    output = BytesIO()
    styles = getSampleStyleSheet()
    font_dir = Path(__file__).resolve().parent / 'assets' / 'fonts'
    if not (font_dir / 'DejaVuSans.ttf').is_file():
        raise RuntimeError('Faltan las fuentes del proyecto en assets/fonts para generar el PDF.')
    if 'NewsSans' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('NewsSans', str(font_dir / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('NewsSans-Bold', str(font_dir / 'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('NewsSans', normal='NewsSans', bold='NewsSans-Bold', italic='NewsSans', boldItalic='NewsSans-Bold')
    for style in styles.byName.values():
        style.splitLongWords = True
        style.fontName = 'NewsSans-Bold' if style.name.startswith(('Heading', 'Title')) else 'NewsSans'
        style.textColor = colors.HexColor('#282744')
    doc = SimpleDocTemplate(output, title='Informe diario · Grupo Boryszew', author='Agente Boryszew',
                            leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    story = []

    def paragraph(text, style='BodyText'):
        story.append(Paragraph(escape(str(text)), styles[style]))
        story.append(Spacer(1, 0.15*cm))

    paragraph('Grupo Boryszew · Informe de noticias', 'Title')
    paragraph(f"Periodo UTC: {report['since']} — {report['until']}")
    paragraph('Resumen del día', 'Heading1')
    paragraph(report['overview'])
    if report['omitted']:
        paragraph(f"Se han omitido {report['omitted']} resultados por el límite de 25 noticias por informe.")
    for index, article in enumerate(report['articles'], 1):
        paragraph(f"{index}. {article['title_es']}", 'Heading2')
        paragraph(f"{article['source']} · {article['published']}")
        paragraph(article['summary_es'])
        url = escape(article['url'], {'"': '&quot;'})
        story.append(Paragraph(f'<link href="{url}" color="#8E1F29">Abrir fuente original</link>', styles['BodyText']))
        paragraph(article['url'])
        paragraph(f"Titular original: {article['title']}")
    paragraph('Cobertura de las fuentes', 'Heading1')
    for channel in report['coverage']:
        paragraph(f"{channel['name']}: {channel['message']} ({channel['count']} resultados en periodo).")
    paragraph('Alcance y limitaciones', 'Heading1')
    paragraph(LIMITATION)

    def footer(canvas, document):
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.setFont('Helvetica', 8)
        canvas.drawString(2*cm, 1*cm, 'Boryszew · Seguimiento de fuentes públicas · Español')
        canvas.drawRightString(19*cm, 1*cm, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
