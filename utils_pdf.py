
---

### 3. **utils_pdf.py**
```python
import io
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def dataframe_to_pdf_bytes(df, title="Zh Scopus Report"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2*cm, height - 2*cm, title)

    c.setFont("Helvetica", 10)
    textobject = c.beginText(2*cm, height - 3*cm)

    # Limit rows/cols for readability
    display_df = df.copy()
    max_cols = 8
    if display_df.shape[1] > max_cols:
        display_df = display_df.iloc[:, :max_cols]
    # Convert to strings and wrap
    col_names = [str(cn) for cn in display_df.columns]
    textobject.textLine(", ".join(col_names))
    textobject.textLine("-"*120)

    max_lines = 35
    line_count = 0
    for _, row in display_df.iterrows():
        row_str = " | ".join(str(v) if v is not None else "" for v in row.tolist())
        if len(row_str) > 220:
            row_str = row_str[:217] + "..."
        textobject.textLine(row_str)
        line_count += 1
        if line_count >= max_lines:
            c.drawText(textobject)
            c.showPage()
            c.setFont("Helvetica", 10)
            textobject = c.beginText(2*cm, height - 2*cm)
            line_count = 0

    c.drawText(textobject)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
