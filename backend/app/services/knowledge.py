import pytesseract
from PIL import Image
import os
from pypdf import PdfReader

def extract_pdf(file_path: str) -> str:
    """Extracts text pages from PDF files safely"""
    try:
        reader = PdfReader(file_path)
        extracted_pages = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            extracted_pages.append(text)
        return "\n".join(extracted_pages)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document structure: {str(e)}")

def parse_document_to_text(file_path: str) -> str:
    """
    Ingests unstructured document files (.pdf, .txt, .png, .jpg, .jpeg, .webp),
    applying image pre-processing and Tesseract OCR text extraction for image catalogs.
    """
    filename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.png', '.jpg', '.jpeg', '.webp']:
        try:
            # 1. Open image via Pillow
            img = Image.open(file_path)
            
            # 2. Convert to Grayscale
            grayscale = img.convert('L')
            
            # 3. Threshold Cleanup (Binarization)
            threshold = 127
            cleaned = grayscale.point(lambda p: 255 if p > threshold else 0)
            
            # 4. OCR Extraction
            ocr_text = pytesseract.image_to_string(cleaned).strip()
            ocr_characters = len(ocr_text)
            
            # 5. Validation: Reject OCR outputs below minimum character threshold
            min_threshold = 10
            if ocr_characters < min_threshold:
                raise ValueError(
                    f"OCR extracted only {ocr_characters} characters, which is below the "
                    f"minimum threshold of {min_threshold} characters. Ingestion rejected."
                )
                
            # Log metrics: filename, ocr_characters, embedding_count estimate (~500 char chunks)
            est_embedding_count = max(1, int(ocr_characters / 500))
            print(
                f"[knowledge_service] Image OCR Succeeded - "
                f"filename={filename}, ocr_characters={ocr_characters}, "
                f"estimated_embedding_count={est_embedding_count}"
            )
            
            return ocr_text
        except Exception as ocr_err:
            print(f"[knowledge_service] [ERROR] OCR pipeline failed for {filename}: {str(ocr_err)}")
            raise ValueError(f"OCR Extraction Failed for image catalog: {str(ocr_err)}")
            
    elif ext == '.pdf':
        pdf_text = extract_pdf(file_path).strip()
        print(f"[knowledge_service] PDF Parsing Succeeded - filename={filename}, characters={len(pdf_text)}")
        return pdf_text
        
    else:
        # Fallback to plain text processing
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_text = f.read().strip()
            print(f"[knowledge_service] Text Parsing Succeeded - filename={filename}, characters={len(raw_text)}")
            return raw_text
        except Exception as txt_err:
            raise ValueError(f"Failed to read plain text file: {str(txt_err)}")
