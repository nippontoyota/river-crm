"""Build the 30-slide visual operations deck from the reviewed reference notes."""
from pathlib import Path
from xml.sax.saxutils import escape
import json
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE as SH, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.xmlchemy import OxmlElement
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

P=Path(__file__).resolve().parents[1]
OLD=json.loads((P/'source/detailed_reference.json').read_text())
C={'ink':'2D1B38','purple':'6945A3','orange':'B65F20','mint':'24776D','red':'AD405D','bg':'F4F0F7','white':'FFFFFF','muted':'776B80','line':'DDD4E6','lavender':'E8DDF4','peach':'F6E3D3','softmint':'DDEDE8','softred':'F4DFE5','darkpanel':'402B50'}
prs=Presentation();prs.slide_width=Inches(13.333333);prs.slide_height=Inches(7.5)
prs.core_properties.title='Incheon Mobility CRM | 30-slide Operations Demo'
prs.core_properties.subject='Visual guide to ownership, lead journeys, complaints and operations'
prs.core_properties.author='Incheon Mobility CRM'
S=[]; cur=None

def rgb(v):return RGBColor.from_string(C.get(v,v))
def rect(sl,x,y,w,h,fill='white',stroke=None,shape=SH.RECTANGLE):
 a=sl.shapes.add_shape(shape,Inches(x),Inches(y),Inches(w),Inches(h))
 a.fill.solid();a.fill.fore_color.rgb=rgb(fill)
 if stroke:a.line.color.rgb=rgb(stroke);a.line.width=Pt(1.2)
 else:a.line.fill.background()
 # Explicitly remove inherited Office shape effects (including drop shadows).
 a._element.spPr.append(OxmlElement('a:effectLst'))
 return a

def text(sl,x,y,w,h,t,size=20,color='ink',bold=False,center=False):
 cur['visible_text'].append(str(t))
 a=sl.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));f=a.text_frame
 f.clear();f.word_wrap=True;f.margin_left=f.margin_right=f.margin_top=f.margin_bottom=0
 for i,line in enumerate(str(t).split('\n')):
  p=f.paragraphs[0] if i==0 else f.add_paragraph();p.text=line;p.font.name='Lato';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color);p.space_after=Pt(5)
  if center:p.alignment=PP_ALIGN.CENTER
 return a

def line(sl,x1,y1,x2,y2,color='purple',width=2,dash=False):
 a=sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2));a.line.color.rgb=rgb(color);a.line.width=Pt(width)
 if dash:
  from pptx.enum.dml import MSO_LINE_DASH_STYLE
  a.line.dash_style=MSO_LINE_DASH_STYLE.DASH
 return a

def dot(sl,x,y,r=.11,fill='purple',stroke=None):return rect(sl,x-r,y-r,r*2,r*2,fill,stroke,SH.OVAL)
def arrow(sl,x,y,color='purple',down=False):
 return rect(sl,x,y,.22 if down else .3,.3 if down else .22,color,shape=SH.DOWN_ARROW if down else SH.CHEVRON)
def pill(sl,x,y,w,t,fill='lavender',color='purple',size=13):
 rect(sl,x,y,w,.39,fill,shape=SH.ROUNDED_RECTANGLE);text(sl,x+.1,y+.07,w-.2,.25,t,size,color,True,True)
def node(sl,x,y,w,label,sub='',color='purple',h=.9):
 rect(sl,x,y,w,h,'white','line',SH.ROUNDED_RECTANGLE);dot(sl,x+.23,y+.26,.06,color)
 text(sl,x+.4,y+.12,w-.55,.33,label,18,color,True)
 if sub:text(sl,x+.17,y+.53,w-.34,.37,sub,14,'muted',center=True)

def icon(sl,x,y,kind,color='purple',s=.65):
 # Small editable line illustrations; no raster assets or external icon dependencies.
 def L(a,b,c,d):line(sl,x+a*s,y+b*s,x+c*s,y+d*s,color,2)
 def R(a,b,w,h):
  a=rect(sl,x+a*s,y+b*s,w*s,h*s,'white',color,SH.ROUNDED_RECTANGLE);a.fill.background()
 if kind=='person':
  a=dot(sl,x+.5*s,y+.23*s,.17*s,'white',color);a.fill.background();L(.17,.9,.17,.66);L(.17,.66,.35,.52);L(.35,.52,.65,.52);L(.65,.52,.83,.66);L(.83,.66,.83,.9)
 elif kind=='calendar':
  R(.08,.18,.84,.74);L(.08,.4,.92,.4);L(.3,.04,.3,.29);L(.7,.04,.7,.29);L(.29,.62,.43,.76);L(.43,.76,.74,.49)
 elif kind=='branch':
  R(.36,.03,.28,.25);R(.02,.69,.28,.25);R(.7,.69,.28,.25);L(.5,.28,.5,.48);L(.16,.48,.84,.48);L(.16,.48,.16,.69);L(.84,.48,.84,.69)
 elif kind=='chart':L(.08,.05,.08,.92);L(.08,.92,.98,.92);L(.3,.77,.3,.55);L(.56,.77,.56,.34);L(.82,.77,.82,.09)
 elif kind=='ticket':R(.07,.2,.86,.63);L(.63,.2,.63,.83);L(.2,.39,.48,.39);L(.2,.6,.48,.6)
 elif kind=='check':
  a=dot(sl,x+.5*s,y+.5*s,.44*s,'white',color);a.fill.background();L(.23,.49,.42,.68);L(.42,.68,.77,.29)
 elif kind=='file':R(.17,.03,.66,.94);L(.31,.29,.7,.29);L(.31,.5,.7,.5);L(.31,.72,.59,.72)
 elif kind=='phone':L(.18,.13,.09,.34);L(.09,.34,.28,.65);L(.28,.65,.65,.92);L(.65,.92,.88,.81);L(.18,.13,.39,.33);L(.39,.33,.28,.46);L(.55,.73,.69,.61);L(.69,.61,.88,.81)
 elif kind=='clock':
  a=dot(sl,x+.5*s,y+.5*s,.44*s,'white',color);a.fill.background();L(.5,.2,.5,.5);L(.5,.5,.76,.65)
 else:R(.1,.1,.8,.8);L(.24,.5,.76,.5)

def new(title,section,subtitle,old=(),note='',dark=False):
 global cur
 paragraphs=[OLD[i-1]['notes'] for i in old]
 refs=list(dict.fromkeys(OLD[i-1]['refs'] for i in old if OLD[i-1]['refs']))
 cur={'title':title,'section':section,'subtitle':subtitle,'notes':note or '\n\n'.join(paragraphs),'refs':'; '.join(refs),'visible_text':[],'old_slides':list(old)};S.append(cur)
 sl=prs.slides.add_slide(prs.slide_layouts[6]);sl.background.fill.solid();sl.background.fill.fore_color.rgb=rgb('ink' if dark else 'bg')
 color='white' if dark else 'ink'
 if not dark:
  text(sl,.6,.34,10,.23,section.upper(),11,'purple',True)
  text(sl,.6,.88,12.1,.7,title,31,color,True)
  text(sl,.62,1.68,12,.48,subtitle,17,'muted')
 line(sl,.6,6.94,12.72,6.94,'darkpanel' if dark else 'line',1)
 text(sl,.6,7.12,8,.2,'INCHEON MOBILITY  /  OPERATIONS DEMO',9,'lavender' if dark else 'muted')
 text(sl,11.75,7.08,.95,.27,f'{len(S):02d} / 30',12,'lavender' if dark else 'purple',True,True)
 return sl

def takeaway(sl,t,color='purple'):
 line(sl,.63,6.44,.99,6.44,color,3);text(sl,1.16,6.26,11.3,.49,t,15,color,True)

def table(sl,rows,widths=None,y=2.47,h=3.57,size=16):
 cols=len(rows[0]);tb=sl.shapes.add_table(len(rows),cols,Inches(.6),Inches(y),Inches(12.12),Inches(h)).table
 widths=widths or ([3.0]+[(12.12-3)/(cols-1)]*(cols-1))
 for i,w in enumerate(widths):tb.columns[i].width=Inches(w)
 for r,row in enumerate(rows):
  for c,v in enumerate(row):
   cur['visible_text'].append(v);ce=tb.cell(r,c);ce.text=v;ce.fill.solid();ce.fill.fore_color.rgb=rgb('ink' if r==0 else ('white' if r%2 else 'lavender'));ce.vertical_anchor=MSO_ANCHOR.MIDDLE
   ce.margin_left=Inches(.14);ce.margin_right=Inches(.1);ce.margin_top=Inches(.055);ce.margin_bottom=Inches(.045)
   for p in ce.text_frame.paragraphs:p.font.name='Lato';p.font.size=Pt(size);p.font.bold=r==0 or c==0;p.font.color.rgb=rgb('white' if r==0 else 'ink')

def journey(sl,items,y=3.55,start=.95,step=3.05):
 line(sl,start+.34,y+.34,start+(len(items)-1)*step+.34,y+.34,'line',6)
 for j,(name,sub,ic,col) in enumerate(items):
  x=start+j*step;dot(sl,x+.34,y+.34,.39,'white',col);icon(sl,x+.08,y+.07,ic,col,.52)
  text(sl,x-.23,y+1,2.55,.38,name,21,col,True,True);text(sl,x-.23,y+1.55,2.55,.7,sub,17,'muted',center=True)

def scenario(title,old,quote,steps,result,proof,color='mint'):
 sl=new(title,'Live scenario',quote,(old,))
 rect(sl,.62,2.45,8.35,3.57,'white',shape=SH.ROUNDED_RECTANGLE)
 # A left-to-right action track; the last panel shows the saved evidence.
 line(sl,1.2,3.25,7.2,3.25,'line',5)
 for j,(h,t,ic) in enumerate(steps):
  x=1.2+j*2.0;dot(sl,x,3.25,.32,'lavender');icon(sl,x-.22,3.02,ic,'purple',.44)
  text(sl,x-.32,3.89,1.81,.62,h,20,'ink',True);text(sl,x-.32,4.65,1.81,.88,t,17,'muted')
 rect(sl,9.24,2.45,3.47,3.57,'softred' if color=='red' else 'softmint',shape=SH.ROUNDED_RECTANGLE)
 icon(sl,10.6,2.82,'check',color,.65);text(sl,9.48,3.7,3,.67,result,27,color,True,True);text(sl,9.59,4.59,2.76,1.01,proof,18,color,center=True)
 takeaway(sl,'Open the same record after saving: verify status, owner and history.',color)

# 01 Cover
sl=new('From enquiry to outcome','Opening','30-slide visual operations walkthrough',(1,),dark=True)
text(sl,.65,.52,10,.3,'INCHEON MOBILITY / CRM',15,'lavender',True)
text(sl,.65,1.6,7.8,1.7,'From enquiry\nto outcome',46,'white',True)
text(sl,.7,3.79,7.1,.85,'People. Decisions. Follow-ups.\nAn operations walkthrough.',24,'lavender')
pill(sl,.7,5.36,3.05,'PRODUCT DEMONSTRATION','darkpanel','white',12)
text(sl,.7,6.2,6,.32,'9 SEPTEMBER 2026',12,'lavender')
# Signature graphic: an actual branching lead path.
line(sl,9.4,2.03,9.4,5.55,'purple',9);line(sl,9.4,3.68,11.7,3.68,'orange',7);line(sl,11.7,3.68,11.7,5.55,'orange',7)
for x,y,n,c in [(9.4,2.03,'CRE','purple'),(9.4,3.68,'PS','purple'),(9.4,5.55,'RETAIL','mint'),(11.7,5.55,'LOST','orange')]:
 dot(sl,x,y,.4,c);text(sl,x-.61,y+.59,1.23,.28,n,13,'white',True,True)

# 02 operating map
sl=new('One enquiry. A visible next owner.','The operating model','Admin → CRE → PS/SO, with branch oversight from the Sales Manager.',(3,4))
line(sl,1.34,3.11,11.88,3.11,'purple',7)
for j,(h,t) in enumerate([('INTAKE','Import / capture'),('CRE','Contact & qualify'),('PS/SO','Follow-up & book'),('RETAIL','Record the sale')]):
 x=1.35+j*3.5;dot(sl,x,3.11,.19,'white','purple');text(sl,x-.71,2.45,1.98,.37,h,19,'purple',True,True);text(sl,x-.8,3.57,2.06,.5,t,17,'muted',center=True)
line(sl,4.85,3.3,4.85,3.42,'orange',3);line(sl,4.85,3.42,3.35,3.42,'orange',3);line(sl,3.35,3.42,3.35,4.79,'orange',3);line(sl,3.35,4.79,6.3,4.79,'orange',3)
pill(sl,2.42,4.95,1.92,'PENDING','peach','orange');pill(sl,5.51,4.95,1.7,'LOST','softred','red')
pill(sl,8.28,4.87,4.26,'SALES MANAGER · BRANCH REVIEW','lavender','purple',12)
text(sl,.75,5.79,11.9,.39,'Complaint path: CRE logs a ticket → Complaints department resolves it',19,'ink',True)

# 03 roles: icons + short responsibilities
sl=new('Six roles, clear responsibilities','People & permissions','Each workspace follows the person’s job.',(5,8,9,10,11))
roles=[('Admin','Allocate · configure · recover work','branch','purple'),('CRE','Contact · qualify · log complaints','phone','purple'),('PS/SO','Follow up · book · retail','check','mint'),('Sales Manager','Review branch · coach owners','chart','purple'),('Complaints','Investigate · resolve · close','ticket','orange'),('Receptionist','Capture walk-ins · select PS','person','orange')]
for j,(h,t,ic,col) in enumerate(roles):
 x=.63+(j%3)*4.13;y=2.46+(j//3)*1.79;rect(sl,x,y,3.81,1.5,'white',shape=SH.ROUNDED_RECTANGLE);icon(sl,x+.2,y+.24,ic,col,.6);text(sl,x+1.0,y+.27,2.61,.43,h,22,col,True);text(sl,x+.23,y+1.01,3.36,.36,t,15,'muted')

# 04-05 preserve matrices
for title,idx in [('Access controls: leads & administration',6),('Access controls: complaints & reporting',7)]:
 d=OLD[idx-1];sl=new(title,'People & permissions',d['subtitle'],(idx,));table(sl,d['body'],[3.12]+[1.5]*6,size=14,h=3.69)
 takeaway(sl,'Capture*: own reception dashboard. Own** / Handoff**: CRE qualification rules apply.' if idx==6 else 'CRE logs. Complaints team resolves. Admin observes.')

# 06 admin hub
sl=new('Admin controls the operating setup','Admin workspace','Set up the team, allocate work, and handle exceptions.',(8,15))
for x,y,w in [(1,2.78,3.1),(9.18,2.78,3.1),(1,4.7,3.1),(9.18,4.7,3.1)]:line(sl,6.63,4.2,x+w/2,y+.51,'line',3)
dot(sl,6.63,4.2,.91,'purple');icon(sl,6.22,3.54,'branch','white',.8);text(sl,5.77,4.57,1.72,.36,'ADMIN',18,'white',True,True)
for x,y,h,t,ic in [(1,2.55,'Users','Roles · active staff · branches','person'),(9.18,2.55,'Lists','Sources · models · colors','file'),(1,4.55,'Allocation','Single lead · filtered bucket','branch'),(9.18,4.55,'Continuity','Reassign · review reminders','calendar')]:
 rect(sl,x,y,3.13,1.22,'white',shape=SH.ROUNDED_RECTANGLE);icon(sl,x+.17,y+.2,ic,'purple',.43);text(sl,x+.77,y+.17,2.21,.4,h,22,'ink',True);text(sl,x+.16,y+.83,2.81,.32,t,14,'muted')
takeaway(sl,'Keep branch names consistent across users, lead records and Admin Lists.')

# 07 intake merging diagram
sl=new('Three entry routes into the CRM','Intake','Sources describe origin; imports and forms bring the enquiries in.',(12,13,33,53))
for j,(h,t,col) in enumerate([('BULK UPLOAD','Admin · CSV / XLSX','purple'),('MANUAL ENQUIRY','Admin / CRE capture','purple'),('SHOWROOM WALK-IN','Receptionist → PS/SO','orange')]):
 y=2.54+j*1.13;node(sl,.7,y,4.58,h,t,col);line(sl,5.28,y+.45,6.3,y+.45,col,2)
line(sl,6.3,2.99,6.3,5.25,'line',3);line(sl,6.3,4.12,7.08,4.12,'purple',3);arrow(sl,7.08,4.01)
node(sl,7.6,3.57,4.87,'Assigned work queue','Fresh allocation or direct qualified lead','purple',1.22)
takeaway(sl,'Walk-ins bypass the CRE allocation step; confirm branch and enquiry date for reporting.')

# 08 table import
sl=new('Check the data before importing','Intake','Review the upload summary, then confirm import.',(13,14,53))
table(sl,[['Check','Current behavior','Operator response'],['CSV / XLSX','Up to 10 MB','Use expected column headers'],['Phone duplicate','Skip CRM or same-file repeats','Review the existing enquiry'],['Name / phone invalid','Skip the invalid row','Correct and re-upload'],['Source / model mismatch','Reject invalid configured value','Use Admin Lists values'],['Enquiry date','Future rejected; missing may default','Confirm the actual enquiry date']],widths=[2.64,4.32,5.16],size=16)
takeaway(sl,'Import duplicate checks do not prevent repeated phone numbers in manual entry.','orange')

# 09 allocation infographic
sl=new('Choose how the batch is shared','Allocation','Individual assignment, filtered buckets, or global Auto assign.',(17,18))
pill(sl,.7,2.36,3.57,'SINGLE LEAD → NAMED CRE');pill(sl,4.64,2.36,3.97,'FILTERED BUCKET → CHOSEN CREs');pill(sl,8.98,2.36,3.7,'AUTO → ELIGIBLE POOL')
text(sl,.72,3.25,3.1,.99,'11 leads\n3 selected CREs',30,'ink',True);text(sl,.73,4.78,3.13,.7,'Equal turns across\nthe new batch',19,'muted')
for j,(name,n,col) in enumerate([('CRE A',4,'purple'),('CRE B',4,'purple'),('CRE C',3,'orange')]):
 y=3.41+j*.84;text(sl,4.4,y-.17,1.4,.4,name,21,col,True)
 for k in range(n):dot(sl,6.55+k*.62,y+.04,.16,col)
 text(sl,9.54,y-.19,.75,.4,str(n),23,col,True)
text(sl,4.4,5.99,7.5,.23,'ILLUSTRATIVE ALLOCATION · NOT COMPANY PERFORMANCE',10,'muted',True)
takeaway(sl,'Use filtered buckets for a scoped demo. Auto assign ignores the active screen filters.','orange')

# 10 hierarchy with oversight separate
sl=new('Branch determines sales ownership and visibility','Allocation','A responsibility map, not an extra approval chain.',(16,44))
node(sl,.73,2.56,3.03,'Admin pool','Allocates CRE','purple');node(sl,4.05,2.56,3.05,'CRE team','Qualifies + selects branch','purple');line(sl,3.76,3.01,4.04,3.01,'purple',2)
line(sl,7.1,3.01,7.7,3.01,'purple',2);line(sl,7.7,3.01,7.7,5.16,'purple',2)
for y,b in [(3.4,'A'),(4.72,'B')]:
 node(sl,8.09,y,4.45,'PS / Branch '+b,'PS location matches selected branch','mint');line(sl,7.7,y+.45,8.09,y+.45,'mint',2)
for y,b in [(3.64,'A'),(4.96,'B')]:
 pill(sl,.84,y,5.42,'SM / BRANCH '+b+' · READ-ONLY OVERSIGHT');line(sl,6.27,y+.2,7.38,y+.2,'muted',2,True)
takeaway(sl,'CRE remains attached after handoff. SM sees records matching their configured branch.')

# 11 decision tree
sl=new('CRE chooses the next path','CRE work','Record what the customer said, then complete the matching fields.',(20,51))
node(sl,4.44,2.4,4.42,'Customer conversation','Review the enquiry and history','purple')
line(sl,6.66,3.3,6.66,3.62,'purple',3);line(sl,2.61,3.62,10.68,3.62,'purple',3)
for x,title,details,col,ic in [(0.72,'QUALIFIED','Model · color · plan · finance\nBranch · PS/SO · notes','mint','check'),(4.77,'PENDING','Reason · remarks\nNext follow-up date','orange','clock'),(8.82,'LOST','Loss reason · remarks\nClose the enquiry','red','file')]:
 line(sl,x+1.84,3.62,x+1.84,3.98,col,3);rect(sl,x,3.98,3.69,1.91,{'mint':'softmint','orange':'peach','red':'softred'}[col],shape=SH.ROUNDED_RECTANGLE);icon(sl,x+.19,4.19,ic,col,.45);text(sl,x+.81,4.25,2.66,.36,title,23,col,True);text(sl,x+.22,5.01,3.25,.7,details,17,col)
takeaway(sl,'Qualification starts the sales handoff; it does not mean a booking or completed sale.')

# 12 qualification checklist infographic
sl=new('A complete qualification makes the handoff useful','CRE → PS/SO','Choose an active PS/SO from the customer’s preferred branch.',(19,21))
fields=[('MODEL + COLOR','What they want','file'),('BUYING PLAN','When they plan to buy','calendar'),('FINANCE','How they plan to pay','file'),('BRANCH + PS/SO','Who acts next','branch'),('REMARKS','What PS should discuss','ticket')]
for j,(h,t,ic) in enumerate(fields):
 x=.71+j*2.51;icon(sl,x+.58,2.62,ic,'purple',.81);text(sl,x,3.8,2.21,.63,h,18,'purple',True,True);text(sl,x,4.67,2.21,.72,t,18,'muted',center=True)
rect(sl,2.97,5.7,7.4,.43,'softmint',shape=SH.ROUNDED_RECTANGLE);text(sl,3.08,5.78,7.18,.25,'SAVE QUALIFIED → SAME LEAD, CRE CONTEXT, NAMED PS',13,'mint',True,True)

# 13 ps table
sl=new('PS/SO records the sales conversation','PS/SO work','Choose Connected / Not Connected, then an outcome and remarks.',(22,23))
table(sl,[['Customer situation','PS outcome examples','Next state'],['Needs more work','Test drive · showroom visit · need time','Pending + follow-up'],['Asks for another call','Call Me Back','Callback + follow-up'],['Does not answer','RNR · Switch Off · Line Busy','Retry / follow-up'],['Has booked / purchased','Booking Done / Retail Done','Booked / Retailed'],['Will not proceed','Finance Rejected · Lost to Competition','Lost']],widths=[3.12,5.15,3.85],size=16)
takeaway(sl,'No Response loss is a manual choice. F1–F5 does not automatically close a lead.','orange')

# 14 followup loop
sl=new('Follow-up is a repeating work cycle','PS/SO & CRE work','A new outcome resolves the previous open follow-up and records the next plan.',(24,23))
rect(sl,.72,2.59,3.15,3.24,'purple',shape=SH.ROUNDED_RECTANGLE);text(sl,1.13,2.97,2.35,.93,'3 days',42,'white',True,True);icon(sl,1.93,4.07,'calendar','white',.7);text(sl,1.03,5.11,2.53,.45,'Current scheduling limit',16,'white',center=True)
# Four connected nodes with a visible return arrow.
for x,y,h,ic in [(4.82,2.65,'SCHEDULE','calendar'),(9.23,2.65,'DUE QUEUE','clock'),(9.23,4.77,'CONTACT','phone'),(4.82,4.77,'RECORD OUTCOME','file')]:
 node(sl,x,y,3.11,h,'','purple',.83)
 # Move node label to accommodate the line icon.
 last=sl.shapes[-1]
line(sl,7.96,3.05,9.03,3.05,'purple',3);arrow(sl,8.78,2.94)
line(sl,10.76,3.51,10.76,4.66,'purple',3);arrow(sl,10.65,4.36,down=True)
line(sl,9.18,5.18,7.96,5.18,'purple',3);arrow(sl,8.05,5.07).rotation=180
line(sl,6.34,4.69,6.34,3.59,'purple',3);arrow(sl,6.23,3.7,down=True).rotation=180;text(sl,7.31,3.98,2.1,.39,'REPEAT',15,'purple',True,True)
takeaway(sl,'CRE / PS selects a day; the current screen saves it at 23:59 IST. Coordinate the next caller.','orange')

# 15 statuses table
sl=new('Translate screen labels into sales events','PS/SO work','Lead status and sales outcome are separate fields.',(25,32))
table(sl,[['Business event','Screen choice','Lead status','Sales outcome'],['Ready for PS','CRE: Qualified','Qualified','Pending'],['Needs more contact','Need time / Visit','Pending','Pending'],['Booking confirmed','Booking Done','Walk-in / Booked','Booked'],['Sale completed','Retail Done','Won / Retailed','Retailed'],['Customer lost','Loss outcome','Lost','Lost']],widths=[3.0,3.16,3.13,2.83],size=16)
takeaway(sl,'A Walk-in source is different from the Walk-in / Booked status.')

# 16 demo menu
sl=new('Five scenarios to demonstrate','Live demo','For each: starting record → staff action → saved result.',(26,))
for j,(name,path,col) in enumerate([('CRE → Qualified','Qualification + branch + named PS','mint'),('CRE → Lost','Loss reason + customer remarks','red'),('Qualified → PS follow-up','Next action + scheduled date','orange'),('Qualified → PS Lost','Sales loss + retained CRE history','red'),('CRE → Complaint','Ticket + complaints-team resolution','purple')]):
 y=2.43+j*.68;dot(sl,.98,y+.2,.18,col);text(sl,.85,y+.07,.26,.25,str(j+1),12,'white',True,True);text(sl,1.44,y+.04,4.8,.39,name,21,col,True);text(sl,6.56,y+.1,5.75,.35,path,18,'muted')

# 17-20 scenario storyboards
scenario('01 / CRE qualifies the enquiry',27,'DEMO ASHA: “I have decided on a model and want to discuss buying.”',[
 ('Open lead','Assigned CRE\nFresh enquiry','person'),('Qualify','Model · plan\nFinance · notes','file'),('Select PS','Preferred branch\nMatching PS/SO','branch'),('Save','Qualify Lead\nRefresh PS queue','check')], 'QUALIFIED','CRE context retained\nPS receives the lead')
scenario('02 / CRE closes a lost enquiry',28,'DEMO BINU: “We have dropped our purchase plan.”',[
 ('Open lead','CRE queue\nCustomer contacted','person'),('Choose Lost','Plan Dropped\nSelected reason','file'),('Explain','Customer-specific\nremarks','ticket'),('Save','Mark as Lost\nCheck history','check')], 'LOST','Reason retained\nNo new follow-up','red')
scenario('03 / PS continues the follow-up',29,'DEMO CHARU: “I need a test drive before deciding.”',[
 ('Read context','Qualified lead\nCRE notes','file'),('Choose outcome','Connected\nNeed Test Drive','phone'),('Set next date','Today / tomorrow\nAdd remarks','calendar'),('Save','Open history\nCheck next action','check')], 'PENDING','Open follow-up\nPS owns next action','orange')
scenario('04 / PS records a sales loss',30,'DEMO DEEPAK: “I have chosen a competing product.”',[
 ('Open lead','Qualified lead\nAssigned PS','person'),('Choose loss','Connected\nLost to Competition','phone'),('Explain','Specific reason\nCustomer remarks','ticket'),('Save','PS Lost view\nSM branch view','check')], 'LOST','CRE history kept\nPS loss recorded','red')

# 21 complaint scenario swimlane
sl=new('05 / CRE hands a complaint to the resolution team','Live scenario','DEMO FARAH: “My delivery issue needs attention.”',(31,35,52))
lanes=[('CRE','Log complaint','Customer · branch\nIssue · priority','purple'),('COMPLAINTS','Work the ticket','In Progress\nAdd resolution remarks','orange'),('CRE / ADMIN','Track the result','Ticket status\nNotes and resolution','mint')]
for j,(role,act,detail,col) in enumerate(lanes):
 y=2.49+j*1.14;rect(sl,.69,y,11.94,.96,'white',shape=SH.ROUNDED_RECTANGLE);pill(sl,.9,y+.28,2.39,role,{'purple':'lavender','orange':'peach','mint':'softmint'}[col],col);icon(sl,3.74,y+.17,'ticket' if j<2 else 'check',col,.56);text(sl,4.66,y+.23,3.48,.4,act,23,col,True);text(sl,8.44,y+.13,3.92,.74,detail,18,'muted')
for y in [3.48,4.63]:arrow(sl,6.35,y,'purple',True)
takeaway(sl,'Complaint is a separate ticket. It does not automatically change or link the sales lead.')

# 22 sales success
sl=new('Complete the sales story','Successful outcome','PS/SO records progress after the company’s sales process supports it.',(32,))
journey(sl,[('QUALIFIED','Read CRE context','file','purple'),('FOLLOW-UP','Resolve questions','phone','purple'),('BOOKED','Booking Done + next date','calendar','orange'),('RETAILED','Retail Done + remarks','check','mint')],y=2.8)
takeaway(sl,'Booking and retail are CRM outcomes; payments, invoicing and inventory remain separate.')

# 23 walkin infographic
sl=new('Walk-ins can go straight to PS/SO','Receptionist flow','Capture the visitor and select the sales user.',(33,12))
journey(sl,[('RECEPTION','Customer · model · color','person','orange'),('SELECT PS','Active sales user','branch','purple'),('QUALIFIED','Walk-in source','check','purple'),('PS FOLLOW-UP','Continue the sales flow','phone','mint')],y=2.65)
rect(sl,.89,5.82,11.52,.63,'peach',shape=SH.ROUNDED_RECTANGLE);text(sl,1.1,5.99,11.1,.31,'REQUIRED OPERATING CHECK: complete branch and enquiry date for manager reporting.',15,'orange',True)

# 24 lifecycle
sl=new('Complaints: shared queue, documented resolution','Complaint operations','Only the complaints department changes status, priority or resolution.',(34,35,36))
line(sl,1.48,3.21,11.88,3.21,'orange',6)
for j,(h,sub,col) in enumerate([('OPEN','CRE logs','purple'),('IN PROGRESS','Resolver investigates','orange'),('RESOLVED','Action + remarks','mint'),('CLOSED','Agreed closure check','mint')]):
 x=1.47+j*3.45;dot(sl,x,3.21,.21,'white',col);text(sl,x-.82,2.49,2.19,.44,h,19,col,True,True);text(sl,x-.79,3.65,2.14,.6,sub,17,'muted',center=True)
line(sl,4.92,3.44,3.48,3.44,'red',3);line(sl,3.48,3.44,3.48,4.6,'red',3);pill(sl,3.48,4.68,2.91,'ESCALATED','softred','red');text(sl,6.97,4.75,5.6,.76,'Updater becomes assignee.\nResolution / closure requires remarks.',21,'ink',True)
takeaway(sl,'Sequence is recommended practice; SLA targets and escalation contacts need agreement.','orange')

# 25 manager lens diagram
sl=new('Sales Manager: inspect, understand, direct','Branch review','Read-only oversight of the configured branch.',(11,38,41))
rect(sl,.75,2.46,3.51,3.38,'purple',shape=SH.ROUNDED_RECTANGLE);icon(sl,2.06,2.82,'chart','white',.9);text(sl,1.04,4.05,2.93,.58,'BRANCH VIEW',26,'white',True,True);text(sl,1.04,4.94,2.93,.62,'Leads · people\nSources · outcomes',20,'white',center=True)
for j,(h,t,ic) in enumerate([('SPOT','Untouched / overdue work','chart'),('OPEN','Lead and owner history','file'),('DIRECT','Owner acts; Admin reallocates','person')]):
 x=4.99+j*2.55;icon(sl,x+.55,2.8,ic,'purple',.7);text(sl,x,3.88,2.34,.4,h,24,'purple',True,True);text(sl,x,4.62,2.34,.85,t,19,'muted',center=True)
takeaway(sl,'Stale = currently Fresh and created at least three calendar days ago.')

# 26 metric table
sl=new('Read dashboard numbers in context','Branch review','Current-state counts support daily review; agree definitions before using targets.',(39,40))
table(sl,[['Measure','What it represents','What to avoid assuming'],['Qualified','Current Qualified status','Everyone who ever qualified'],['Booked / Retailed','Current sales outcome','An immutable sales ledger'],['Contacted','Status is no longer Fresh','Verified connected call'],['Lead-to-retail %','Retailed ÷ selected lead cohort','Same cohort across different filters'],['Lost reasons','Call outcomes on currently lost leads','One final reason per unique lead']],widths=[2.48,4.72,4.92],size=16)
takeaway(sl,'Keep branch and date filters visible; open records to explain the count.','orange')

# 27 daily operating timeline
sl=new('Make the queues part of the working day','Daily operations','Suggested rhythm; agree timings with the manager.',(37,))
line(sl,1.41,3.31,11.85,3.31,'purple',6)
for j,(time,who,act,col) in enumerate([('START','ADMIN','Allocate new work\nCheck reassignment','purple'),('THROUGHOUT','CRE / PS','Contact customer\nSave outcome + next date','purple'),('MIDDAY','SALES MANAGER','Review gaps\nDirect owners','orange'),('DAY END','TEAM LEADS','Clear exceptions\nConfirm next owners','mint')]):
 x=1.4+j*3.48;dot(sl,x,3.31,.23,col);text(sl,x-.8,2.61,2.3,.42,time,21,col,True,True);text(sl,x-.8,3.87,2.3,.4,who,17,col,True,True);text(sl,x-.8,4.64,2.3,.94,act,20,'muted',center=True)
takeaway(sl,'Complaints need their own queue review and escalation owner.')

# 28 exception table
sl=new('Exceptions: what staff should do next','Operational controls','Keep the customer record and next owner clear.',(42,47))
table(sl,[['Exception','Current handling','Operator action'],['No matching active PS','Qualification cannot complete','Admin checks branch and staffing'],['Already assigned / conflicting save','Dedicated action rejects conflict','Refresh; read owner and history'],['Invalid follow-up date','Save rejected','Use today / tomorrow within limit'],['SM cannot see the lead','Branch or dates may exclude it','Check branch, enquiry date, filters'],['Reminder not visible','Live delivery needs verification','Use due queues; confirm scheduler']],widths=[3.34,4.03,4.75],size=16)
takeaway(sl,'Reopen and escalation flags lack a complete visible workflow; verify before promising them.','orange')

# 29 offboarding split path
sl=new('Staff changes need two handovers','Operational continuity','Dedicated lifecycle flow for CRE and PS/SO.',(43,44,45,46))
node(sl,.73,2.5,3.39,'Preview impact','Active / closed work','purple');node(sl,4.98,2.5,3.39,'Choose routes','Pool or distribute by status','purple');node(sl,9.23,2.5,3.39,'Disable / delete','Keep historical attribution','purple')
for x in [4.34,8.59]:arrow(sl,x,2.85)
line(sl,6.67,3.43,6.67,3.86,'purple',3);line(sl,3.48,3.86,9.87,3.86,'purple',3)
for x,h,t,col,ic in [(0.77,'1 / LEAD OWNERSHIP','Active replacements; PS branch must match.\nUnmatched work → Needs reassignment.','purple','branch'),(7.15,'2 / FOLLOW-UP REMINDERS','Hold inherited reminders.\nAdmin approves, reschedules or resolves.','orange','calendar')]:
 line(sl,x+2.72,3.86,x+2.72,4.15,col,3);rect(sl,x,4.15,5.44,1.79,'white',shape=SH.ROUNDED_RECTANGLE);icon(sl,x+.24,4.4,ic,col,.48);text(sl,x+.98,4.48,4.14,.4,h,19,col,True);text(sl,x+.24,5.11,4.96,.72,t,17,'muted')
takeaway(sl,'Re-enable does not return transferred leads. Deleted accounts cannot be re-enabled.')

# 30 closing decisions
sl=new('Agree the rules for the pilot','Next steps','Leave the meeting with named owners and a short decision list.',(48,49,54),dark=True)
text(sl,.64,.39,11,.25,'OPERATING DECISIONS',12,'lavender',True);text(sl,.64,1.05,11.9,.75,'Agree the rules for the pilot',36,'white',True)
for j,(h,t,ic) in enumerate([('ALLOCATION','Cadence + accountable Admin','branch'),('NEXT CONTACT','PS ownership after handoff','phone'),('RETRY POLICY','Attempts + evidence for loss','clock'),('COMPLAINTS','Priority targets + escalation','ticket'),('REPORTING','Accepted metric definitions','chart')]):
 x=.7+j*2.52;icon(sl,x+.65,2.61,ic,'lavender',.71);text(sl,x,3.87,2.28,.54,h,18,'white',True,True);text(sl,x,4.69,2.28,.89,t,19,'lavender',center=True)
text(sl,.82,6.23,11.7,.43,'Record the decision · name the owner · agree what must change before rollout',20,'white',True,True)

assert len(S)==30
for i,(sl,d) in enumerate(zip(prs.slides,S),1):
 sl.notes_slide.notes_text_frame.text=f"SLIDE {i}: {d['title']}\n\nPRESENTER NOTES\n{d['notes']}\n\nEVIDENCE\n{d['refs'] or 'Proposed operating practice; not an enforced product rule.'}"
prs.save(P/'Incheon_Mobility_Operations_Demo.pptx')
(P/'source/slide_content.json').write_text(json.dumps(S,ensure_ascii=False,indent=2))
md=['# Incheon Mobility CRM — 30-slide presenter notes','Revised visual edition. Details remain in the notes; the presentation uses short labels and infographics.','']
for i,d in enumerate(S,1):md += [f"## Slide {i:02d} — {d['title']}",d['subtitle'],'',d['notes'],'',f"Evidence: {d['refs']}",'']
(P/'Presenter_Notes.md').write_text('\n'.join(md))
for name,file in [('Lato','Lato-Regular.ttf'),('Lato-Bold','Lato-Bold.ttf')]:pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/lato/'+file))
pdfmetrics.registerFontFamily('Lato',normal='Lato',bold='Lato-Bold')
styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='T',fontName='Lato-Bold',fontSize=22,leading=28,textColor=HexColor('#2D1B38'),spaceAfter=15));styles.add(ParagraphStyle(name='B',fontName='Lato',fontSize=10.5,leading=15,spaceAfter=11));styles.add(ParagraphStyle(name='R',fontName='Lato',fontSize=8,leading=11,textColor=HexColor('#776B80'),spaceAfter=8))
story=[Paragraph('Incheon Mobility CRM<br/>30-slide presenter notes',styles['T']),Paragraph('Visual edition · 9 September 2026. Detailed notes merge the earlier reference material. Use PowerPoint Presenter View for the live session. Some combined notes span more than one printed page.',styles['B'])]
for i,d in enumerate(S,1):
 story += [PageBreak(),Paragraph(f'SLIDE {i:02d} / 30',styles['R']),Paragraph(escape(d['title']),styles['T'])]
 for p in d['notes'].split('\n\n'):story.append(Paragraph(escape(p),styles['B']))
 story.append(Paragraph('Evidence: '+escape(d['refs'] or 'Proposed operating practice.'),styles['R']))
def footer(can,doc):
 can.setFont('Lato',8);can.setFillColor(HexColor('#776B80'));can.drawString(43,25,'INCHEON MOBILITY / PRESENTER NOTES / VISUAL EDITION');can.drawRightString(552,25,str(doc.page))
SimpleDocTemplate(str(P/'Presenter_Notes.pdf'),pagesize=(595,842),leftMargin=43,rightMargin=43,topMargin=45,bottomMargin=47,title='Incheon Mobility CRM | 30-slide presenter notes',author='Incheon Mobility CRM').build(story,onFirstPage=footer,onLaterPages=footer)
print('Built 30 visual slides with full presenter notes.')
