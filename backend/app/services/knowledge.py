import pytesseract
from PIL import Image
import os
from pypdf import PdfReader

def extract_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    extracted_pages = []
    for page in reader.pages:
        extracted_pages.append(page.extract_text() or "")
    return "\n".join(extracted_pages)

def parse_document_to_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.png', '.jpg', '.jpeg']:
        # Execute OCR parsing for structural text extraction
        return pytesseract.image_to_string(Image.open(file_path))
    elif ext == '.pdf':
        return extract_pdf(file_path)
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
