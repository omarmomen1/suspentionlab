from fastapi import APIRouter, Response, Request
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

router = APIRouter()

@router.get("/docs/api-reference.pdf")
async def get_api_reference_pdf(request: Request):
    openapi_data = request.app.openapi()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=54, 
        leftMargin=54,
        topMargin=54, 
        bottomMargin=54
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#1A365D'),
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#4A5568'),
        spaceAfter=20
    )
    
    heading2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#2B6CB0'),
        spaceBefore=15,
        spaceAfter=10,
        keepWithNext=True
    )

    heading3_style = ParagraphStyle(
        'Heading3Custom',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2D3748'),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#2D3748'),
        spaceAfter=8
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white
    )
    
    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#2D3748')
    )

    info = openapi_data.get('info', {})
    story.append(Paragraph(info.get('title', 'FastAPI API Reference'), title_style))
    story.append(Paragraph(f"Version: {info.get('version', '1.0.0')}", subtitle_style))
    if 'description' in info:
        story.append(Paragraph(info['description'], body_style))
    
    story.append(Spacer(1, 20))
    story.append(PageBreak())
    
    paths = openapi_data.get('paths', {})
    tags_map = {}
    for path, path_info in paths.items():
        for method, method_info in path_info.items():
            if method.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                continue
            tags = method_info.get('tags', ['Default'])
            for tag in tags:
                if tag not in tags_map:
                    tags_map[tag] = []
                tags_map[tag].append((path, method, method_info))
                
    for tag, endpoints in sorted(tags_map.items()):
        story.append(Paragraph(f"{tag} Endpoints", heading2_style))
        story.append(Spacer(1, 5))
        
        for path, method, info in endpoints:
            endpoint_header = f"<b>{method.upper()}</b> {path}"
            story.append(Paragraph(endpoint_header, heading3_style))
            
            summary = info.get('summary', '')
            description = info.get('description', '')
            if summary:
                story.append(Paragraph(f"<i>Summary:</i> {summary}", body_style))
            if description:
                story.append(Paragraph(description, body_style))
                
            params = info.get('parameters', [])
            if params:
                story.append(Paragraph("<b>Parameters:</b>", body_style))
                table_data = [[Paragraph("Name", table_header_style), Paragraph("In", table_header_style), Paragraph("Type", table_header_style), Paragraph("Required", table_header_style), Paragraph("Description", table_header_style)]]
                for p in params:
                    p_type = p.get('schema', {}).get('type', 'string')
                    table_data.append([
                        Paragraph(p.get('name', ''), table_body_style),
                        Paragraph(p.get('in', ''), table_body_style),
                        Paragraph(p_type, table_body_style),
                        Paragraph(str(p.get('required', False)), table_body_style),
                        Paragraph(p.get('description', ''), table_body_style)
                    ])
                t = Table(table_data, colWidths=[100, 50, 70, 60, 220])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')])
                ]))
                story.append(t)
                story.append(Spacer(1, 8))
                
            req_body = info.get('requestBody')
            if req_body:
                story.append(Paragraph("<b>Request Body:</b>", body_style))
                content = req_body.get('content', {})
                for media_type, media_info in content.items():
                    schema = media_info.get('schema', {})
                    ref = schema.get('$ref', '')
                    if ref:
                        schema_name = ref.split('/')[-1]
                        story.append(Paragraph(f"Content Type: <code>{media_type}</code> (Schema: {schema_name})", body_style))
                    else:
                        story.append(Paragraph(f"Content Type: <code>{media_type}</code>", body_style))
            
            responses = info.get('responses', {})
            if responses:
                story.append(Paragraph("<b>Responses:</b>", body_style))
                resp_data = [[Paragraph("Code", table_header_style), Paragraph("Description", table_header_style), Paragraph("Schema", table_header_style)]]
                for code, resp_info in responses.items():
                    desc = resp_info.get('description', '')
                    schema_str = '-'
                    resp_content = resp_info.get('content', {})
                    for mt, mi in resp_content.items():
                        r_schema = mi.get('schema', {})
                        r_ref = r_schema.get('$ref', '')
                        if r_ref:
                            schema_str = r_ref.split('/')[-1]
                        else:
                            schema_str = r_schema.get('type', 'any')
                    resp_data.append([
                        Paragraph(code, table_body_style),
                        Paragraph(desc, table_body_style),
                        Paragraph(schema_str, table_body_style)
                    ])
                rt = Table(resp_data, colWidths=[50, 300, 150])
                rt.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4A5568')),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')])
                ]))
                story.append(rt)
                
            story.append(Spacer(1, 15))
            
    doc.build(story)
    pdf_content = buffer.getvalue()
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=api-reference.pdf"}
    )
