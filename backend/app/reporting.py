"""PDF report builder for sentiment summaries and negative-post evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor('#12263A')
BLUE = colors.HexColor('#1877F2')
RED = colors.HexColor('#C83E3A')
GREEN = colors.HexColor('#278D75')
AMBER = colors.HexColor('#B8751A')
INK = colors.HexColor('#17202D')
MUTED = colors.HexColor('#667085')
LINE = colors.HexColor('#D9E1EA')
PALE = colors.HexColor('#F3F6FA')
RED_PALE = colors.HexColor('#FFF2F1')
WHITE = colors.white

FONT_DIR = Path(__file__).with_name('assets') / 'fonts'


def _fonts() -> tuple[str, str]:
    """Use the bundled Unicode font so Hindi titles do not become black boxes."""
    regular = FONT_DIR / 'NotoSansDevanagari.ttf'
    latin = FONT_DIR / 'NotoSans.ttf'
    try:
        if 'JanNetraSans' not in pdfmetrics.getRegisteredFontNames():
            # Noto Sans Devanagari also contains Latin glyphs, so one font can
            # safely render English, Hinglish, and Hindi in the same paragraph.
            pdfmetrics.registerFont(TTFont('JanNetraSans', str(regular)))
            pdfmetrics.registerFont(TTFont('JanNetraSansBold', str(regular)))
        return 'JanNetraSans', 'JanNetraSansBold'
    except Exception:
        # The second bundled font still gives a readable report if a runtime
        # cannot load the Devanagari variable font.
        try:
            if 'JanNetraSans' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('JanNetraSans', str(latin)))
                pdfmetrics.registerFont(TTFont('JanNetraSansBold', str(latin)))
            return 'JanNetraSans', 'JanNetraSansBold'
        except Exception:
            return 'Helvetica', 'Helvetica-Bold'


def _clean(value: object, limit: int | None = None) -> str:
    # The bundled report font covers Latin and Devanagari. Drop supplementary
    # emoji codepoints which would otherwise render as distracting empty boxes.
    text = ''.join(char for char in str(value or '') if ord(char) <= 0xFFFF)
    text = ' '.join(text.split())
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + '...'
    return escape(text)


def _link(url: object) -> str | None:
    value = str(url or '').strip()
    if not value.startswith(('https://', 'http://')):
        return None
    # Quote only characters which are unsafe inside a ReportLab href attribute.
    return quote(value, safe=':/?&=#%+@;,$!~*()[]-_')


def _published(value: object, timezone_name: str) -> str:
    if isinstance(value, datetime):
        try:
            from zoneinfo import ZoneInfo
            return value.astimezone(ZoneInfo(timezone_name)).strftime('%d %b %Y, %I:%M %p')
        except Exception:
            return value.strftime('%d %b %Y, %I:%M %p')
    return _clean(value) or 'Time unavailable'


def build_sentiment_pdf(
    stream,
    *,
    start: str,
    end: str,
    period: str,
    timezone_name: str,
    rows: list[dict],
    negative_posts: list[dict],
    source_rows: list[dict],
    demo: bool = False,
) -> None:
    regular, bold = _fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='JNTitle', fontName=bold, fontSize=24, leading=30, textColor=NAVY, spaceAfter=4))
    styles.add(ParagraphStyle(name='JNSubtitle', fontName=regular, fontSize=9, leading=13, textColor=MUTED))
    styles.add(ParagraphStyle(name='JNSection', fontName=bold, fontSize=14, leading=18, textColor=NAVY, spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name='JNPlatform', fontName=bold, fontSize=16, leading=20, textColor=NAVY, spaceAfter=4))
    styles.add(ParagraphStyle(name='JNBody', fontName=regular, fontSize=8.6, leading=12.5, textColor=INK, splitLongWords=True))
    styles.add(ParagraphStyle(name='JNMeta', fontName=regular, fontSize=7.4, leading=10.5, textColor=MUTED))
    styles.add(ParagraphStyle(name='JNLink', fontName=bold, fontSize=8, leading=11, textColor=BLUE))
    styles.add(ParagraphStyle(name='JNMetric', fontName=bold, fontSize=19, leading=22, textColor=INK, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='JNMetricLabel', fontName=regular, fontSize=7, leading=9, textColor=MUTED, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='JNTableHead', fontName=bold, fontSize=7.3, leading=9, textColor=WHITE, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='JNTable', fontName=regular, fontSize=7.2, leading=9, textColor=INK, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='JNTableLeft', parent=styles['JNTable'], alignment=TA_LEFT))

    page_w, page_h = A4
    left = right = 17 * mm
    top = 22 * mm
    bottom = 17 * mm
    doc = BaseDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=f'JanNetra {period.title()} Sentiment Report',
        author='JanNetra',
        subject='Sentiment summary and negative-post evidence',
    )
    frame = Frame(left, bottom, page_w - left - right, page_h - top - bottom, id='report-frame', showBoundary=0)

    def page_chrome(canvas, document):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_h - 10 * mm, page_w, 10 * mm, fill=1, stroke=0)
        canvas.setFont(bold, 9)
        canvas.setFillColor(WHITE)
        canvas.drawString(left, page_h - 6.5 * mm, 'JanNetra  |  Political conversation intelligence')
        canvas.setStrokeColor(LINE)
        canvas.line(left, 12 * mm, page_w - right, 12 * mm)
        canvas.setFont(regular, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(left, 7.5 * mm, f'{start} to {end}  |  {timezone_name}')
        canvas.drawRightString(page_w - right, 7.5 * mm, f'Page {document.page}')
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id='report', frames=[frame], onPage=page_chrome))

    by_platform: dict[str, list[dict]] = defaultdict(list)
    for post in negative_posts:
        by_platform[str(post.get('platform') or 'unknown')].append(post)

    total_positive = sum(int(r.get('positive_count', 0)) for r in rows)
    total_negative = sum(int(r.get('negative_count', 0)) for r in rows)
    total_neutral = sum(int(r.get('neutral_count', 0)) for r in rows)
    total_mixed = sum(int(r.get('mixed_count', 0)) for r in rows)
    total_classified = sum(int(r.get('total_count', 0)) for r in rows)
    negativity = (total_negative / total_classified * 100) if total_classified else 0

    story = [
        Spacer(1, 4 * mm),
        Paragraph('JanNetra Sentiment Report' + ('  |  DEMO DATA' if demo else ''), styles['JNTitle']),
        Paragraph(
            f'{period.title()} report &nbsp;&nbsp;|&nbsp;&nbsp; {_clean(start)} to {_clean(end)} '
            f'&nbsp;&nbsp;|&nbsp;&nbsp; Generated for {escape(timezone_name)}',
            styles['JNSubtitle'],
        ),
        Spacer(1, 7 * mm),
    ]

    metrics = [
        ('CLASSIFIED', total_classified, INK),
        ('POSITIVE', total_positive, GREEN),
        ('NEGATIVE', total_negative, RED),
        ('NEUTRAL', total_neutral, MUTED),
        ('MIXED', total_mixed, AMBER),
        ('NEGATIVITY', f'{negativity:.1f}%', RED),
    ]
    metric_cells = []
    for label, value, color in metrics:
        value_style = ParagraphStyle(name=f'JNMetric-{label}', parent=styles['JNMetric'], textColor=color)
        metric_cells.append([Paragraph(str(value), value_style), Paragraph(label, styles['JNMetricLabel'])])
    metric_table = Table([metric_cells], colWidths=[(page_w - left - right) / 6] * 6, rowHeights=[20 * mm])
    metric_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('INNERGRID', (0, 0), (-1, -1), .4, LINE),
        ('BACKGROUND', (0, 0), (-1, -1), PALE),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.extend([metric_table, Spacer(1, 6 * mm), Paragraph('Platform summary', styles['JNSection'])])

    summary_header = ['Date', 'Platform', 'Positive', 'Negative', 'Neutral', 'Mixed', 'Total', 'Negativity']
    summary_data = [[Paragraph(x, styles['JNTableHead']) for x in summary_header]]
    for row in rows:
        summary_data.append([
            Paragraph(_clean(row.get('date')), styles['JNTableLeft']),
            Paragraph(_clean(str(row.get('platform', '')).title()), styles['JNTableLeft']),
            Paragraph(str(row.get('positive_count', 0)), styles['JNTable']),
            Paragraph(str(row.get('negative_count', 0)), styles['JNTable']),
            Paragraph(str(row.get('neutral_count', 0)), styles['JNTable']),
            Paragraph(str(row.get('mixed_count', 0)), styles['JNTable']),
            Paragraph(str(row.get('total_count', 0)), styles['JNTable']),
            Paragraph(f"{float(row.get('negativity_index', 0)):.1f}%", styles['JNTable']),
        ])
    summary = Table(summary_data, repeatRows=1, colWidths=[21*mm, 24*mm, 19*mm, 19*mm, 18*mm, 16*mm, 17*mm, 23*mm])
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, PALE]),
        ('GRID', (0, 0), (-1, -1), .35, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([summary, Spacer(1, 5 * mm), Paragraph('Data source status', styles['JNSection'])])

    source_data = [[Paragraph('Platform', styles['JNTableHead']), Paragraph('Source', styles['JNTableHead']), Paragraph('Status', styles['JNTableHead'])]]
    for source in source_rows:
        source_data.append([
            Paragraph(_clean(str(source.get('platform', '')).title()), styles['JNTableLeft']),
            Paragraph(_clean(source.get('source')), styles['JNTableLeft']),
            Paragraph(_clean(source.get('status')), styles['JNTableLeft']),
        ])
    sources = Table(source_data, repeatRows=1, colWidths=[40*mm, 75*mm, 45*mm])
    sources.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, PALE]),
        ('GRID', (0, 0), (-1, -1), .35, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([
        sources,
        Spacer(1, 7 * mm),
        Paragraph('Negative-post evidence', styles['JNSection']),
        Paragraph(
            f'{len(negative_posts)} negative posts are listed below. Each available source URL is embedded as a clickable link.',
            styles['JNSubtitle'],
        ),
    ])

    platform_order = ['facebook', 'instagram', 'x', 'youtube', 'news']
    for platform in platform_order + sorted(set(by_platform) - set(platform_order)):
        posts = by_platform.get(platform, [])
        if not posts:
            continue
        story.extend([
            PageBreak(),
            Paragraph(f'{escape(platform.title())} negative posts', styles['JNPlatform']),
            Paragraph(f'{len(posts)} posts in the selected period', styles['JNSubtitle']),
            Spacer(1, 4 * mm),
        ])
        for index, post in enumerate(posts, 1):
            sentiment = post.get('sentiment') or {}
            engagement = post.get('engagement') or {}
            confidence = round(float(sentiment.get('confidence', 0)) * 100)
            engagement_total = int(post.get('engagement_score') or (
                int(engagement.get('likes', 0)) + int(engagement.get('comments', 0)) + int(engagement.get('shares', 0))
            ))
            url = _link(post.get('url'))
            link_text = f'<link href="{url}" color="#1877F2"><u>Open original post</u></link>' if url else 'Original link unavailable'
            heading = Paragraph(
                f'<b>#{index}</b>&nbsp;&nbsp; {_clean(post.get("author") or "Unknown author", 100)}',
                styles['JNBody'],
            )
            meta = Paragraph(
                f'{_published(post.get("published_at"), timezone_name)} &nbsp;&nbsp;|&nbsp;&nbsp; '
                f'Confidence {confidence}% &nbsp;&nbsp;|&nbsp;&nbsp; Engagement {engagement_total:,}',
                styles['JNMeta'],
            )
            body = Paragraph(_clean(post.get('content') or 'Content unavailable'), styles['JNBody'])
            link_para = Paragraph(link_text, styles['JNLink'])
            card = Table([[heading], [meta], [body], [link_para]], colWidths=[page_w - left - right - 8*mm])
            card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 1), RED_PALE),
                ('BOX', (0, 0), (-1, -1), .55, LINE),
                ('LINEBELOW', (0, 1), (-1, 1), .35, LINE),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([KeepTogether([card, Spacer(1, 3 * mm)])])

    if not negative_posts:
        story.extend([Spacer(1, 5 * mm), Paragraph('No classified negative posts were found in this reporting period.', styles['JNBody'])])

    doc.build(story)
