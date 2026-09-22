"""
Lundayang Marians - Batch Scanned PDF to Searchable PDF Converter
-----------------------------------------------------------------
This utility allows administrators and panels to convert scanned ("picture-to-PDF")
papers into fully searchable and selectable PDFs ("Sandwich PDFs") automatically,
without having to manually retype or rewrite a single word in Microsoft Word!

How it works:
- Scans each page of the input PDF using OCR (Optical Character Recognition).
- Embeds an invisible text layer with exact character coordinates directly behind
  the scanned page image.
- Outputs a searchable PDF that can be uploaded to Lundayang Marians. When opened,
  users can highlight, select, and copy text naturally.

Prerequisites:
  pip install ocrmypdf
  (On Windows, ocrmypdf requires Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki)

Usage:
  # Convert a single PDF file:
  python scripts/batch_ocr_pdf.py -i input_scanned.pdf -o output_searchable.pdf

  # Convert an entire folder of scanned PDFs:
  python scripts/batch_ocr_pdf.py -d path/to/scanned_folder -o path/to/output_folder
"""

import sys
import os
import argparse

def convert_single_pdf(input_path: str, output_path: str, deskew: bool = True):
    try:
        import ocrmypdf
    except ImportError:
        print("\n[ERROR] 'ocrmypdf' is not installed.")
        print("Please install it using: pip install ocrmypdf")
        print("Note: On Windows, also install Tesseract-OCR: https://github.com/UB-Mannheim/tesseract/wiki\n")
        return False

    print(f"[OCR] Processing: '{input_path}' -> '{output_path}'...")
    try:
        ocrmypdf.ocr(
            input_path,
            output_path,
            deskew=deskew,
            skip_text=True, # Skip pages that already have digital text
            force_ocr=False
        )
        print(f"[SUCCESS] Searchable PDF created at: {output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to convert {input_path}: {e}")
        return False

def convert_directory(input_dir: str, output_dir: str):
    if not os.path.isdir(input_dir):
        print(f"[ERROR] Directory not found: {input_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"[INFO] No PDF files found in {input_dir}")
        return

    print(f"[INFO] Found {len(pdf_files)} PDF file(s) to process.\n")
    success_count = 0
    for idx, filename in enumerate(pdf_files, 1):
        in_file = os.path.join(input_dir, filename)
        out_file = os.path.join(output_dir, filename)
        print(f"[{idx}/{len(pdf_files)}] {filename}")
        if convert_single_pdf(in_file, out_file):
            success_count += 1

    print(f"\n[SUMMARY] Successfully processed {success_count}/{len(pdf_files)} PDF(s).")

def main():
    parser = argparse.ArgumentParser(description="Lundayang Marians - Scanned PDF to Searchable PDF Converter")
    parser.add_argument("-i", "--input", help="Path to input scanned PDF file")
    parser.add_argument("-o", "--output", help="Path to output searchable PDF file or directory")
    parser.add_argument("-d", "--dir", help="Path to folder containing multiple scanned PDF files")
    parser.add_argument("--no-deskew", action="store_true", help="Disable automatic page deskewing")

    args = parser.parse_args()

    if args.dir:
        out_dir = args.output or os.path.join(args.dir, "searchable_pdfs")
        convert_directory(args.dir, out_dir)
    elif args.input:
        out_file = args.output
        if not out_file:
            base, ext = os.path.splitext(args.input)
            out_file = f"{base}_searchable{ext}"
        convert_single_pdf(args.input, out_file, deskew=not args.no_deskew)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
