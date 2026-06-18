---
name: file-conversion
description: Convert between PDF, DOCX, XLSX, images, audio formats. Python libraries for document processing pipelines.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔄
    requires: {bins: [python], env: []}
---

# File Conversion

## Overview
Convert files between formats using Python libraries. Handle PDF extraction, document conversion, image processing.

## Tools
- `python-docx` — .docx read/write
- `openpyxl` — .xlsx read/write
- `PyPDF2`/`pdfplumber` — PDF text extraction
- `Pillow` — image format conversion
- `pandas` — CSV/Excel/JSON/Parquet conversion
- `markdown` + `weasyprint` — MD to PDF

## Process
1. Identify source format and encoding
2. Choose conversion library appropriate to format
3. Extract content preserving structure where possible
4. Handle encoding errors gracefully (try UTF-8, then Latin-1, then replace)
5. Verify output: spot-check converted content against source

## Anti-Patterns
- Don't assume PDFs have extractable text (scanned PDFs need OCR)
- Don't convert without checking encoding
- Don't lose metadata (author, date, title) during conversion
