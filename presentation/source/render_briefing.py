from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
P=Path(__file__).resolve().parents[1]
for name,path in [('Lato','/usr/share/fonts/truetype/lato/Lato-Regular.ttf'),('LatoBold','/usr/share/fonts/truetype/lato/Lato-Bold.ttf')]:pdfmetrics.registerFont(TTFont(name,path))
pdfmetrics.registerFontFamily('Lato',normal='Lato',bold='LatoBold')
s=getSampleStyleSheet()
s.add(ParagraphStyle(name='T',fontName='LatoBold',fontSize=23,leading=28,spaceAfter=17,textColor=HexColor('#2D1B38')))
s.add(ParagraphStyle(name='H',fontName='LatoBold',fontSize=15,leading=20,spaceBefore=16,spaceAfter=9,textColor=HexColor('#6945A3'),keepWithNext=True))
s.add(ParagraphStyle(name='h',fontName='LatoBold',fontSize=12,leading=16,spaceBefore=12,spaceAfter=7,keepWithNext=True))
s.add(ParagraphStyle(name='B',fontName='Lato',fontSize=10.5,leading=15,spaceAfter=8))
s.add(ParagraphStyle(name='cell',fontName='Lato',fontSize=8.5,leading=12))
def fmt(t):return re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',escape(t)).replace('`','')
lines=(P/'START_HERE_Demo_Briefing.md').read_text().splitlines();story=[];i=0
while i<len(lines):
 t=lines[i]
 if t.startswith('|'):
  rows=[]
  while i<len(lines) and lines[i].startswith('|'):
   if not re.fullmatch(r'[|\- :]+',lines[i]):rows.append([Paragraph(fmt(v.strip()),s['cell']) for v in lines[i].strip('|').split('|')])
   i+=1
  tab=Table(rows,colWidths=[509/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign='LEFT')
  tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#E8DDF4')),('ROWBACKGROUNDS',(0,1),(-1,-1),[HexColor('#F4F0F7'),HexColor('#FFFFFF')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story+=[tab,Spacer(1,9)];continue
 if t.startswith('# '):sty='T';t=t[2:]
 elif t.startswith('## '):sty='H';t=t[3:]
 elif t.startswith('### '):sty='h';t=t[4:]
 else:sty='B';t=t.removeprefix('> ')
 if t.strip():story.append(Paragraph(fmt(t),s[sty]))
 i+=1
def footer(can,doc):
 can.setFont('Lato',8);can.setFillColor(HexColor('#776B80'));can.drawString(43,25,'INCHEON MOBILITY CRM | DEMO BRIEFING | PRESENTER COPY');can.drawRightString(552,25,str(doc.page))
SimpleDocTemplate(str(P/'START_HERE_Demo_Briefing.pdf'),pagesize=(595,842),leftMargin=43,rightMargin=43,topMargin=43,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
print('Briefing PDF built.')
