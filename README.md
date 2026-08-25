# Office Translate Pro

Automatic professional translation skills for Word, Excel, PowerPoint, PDF, PNG, and JPEG with cement-industry terminology and layout fidelity.

PDF files use a second-level router. Native-text and mixed PDFs are handled by `formats/pdf/native`; scan-only/image-only PDFs are handled independently by `formats/pdf/scan`.

Static PNG and JPEG images use `formats/image`, which bridges each image through the scan-PDF workflow and restores the original image format and pixel dimensions.
