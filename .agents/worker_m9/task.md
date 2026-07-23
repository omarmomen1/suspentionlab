# Milestone 9: API Versioning and Documentation

## Objectives
1. Fix the compile-blocking syntax errors in `src/suspensionlab/backend/api/main.py` (missing commas in route inclusions).
2. Refactor router mounting in `main.py` so that ALL routes (except root `/`, `/health`, `/ready`, `/metrics`, etc.) are consistently mounted under the `/api/v1/` prefix.
3. Expose the OpenAPI document as a PDF at the endpoint `/docs/api-reference.pdf`.
4. Update `requirements-backend.txt` to include `reportlab` (and resolve any packaging syntax typos).

## Guidelines
- Write clean, robust python code.
- Generate ReportLab elements (Paragraph, Table, PageBreak, etc.) dynamically by parsing the FastAPI `app.openapi()` dictionary (tags, paths, methods, schemas) to construct a readable API documentation.
- Serves the generated PDF as a Response with `application/pdf` media type.
- Verify that python compiles and FastAPI runs successfully.

## Verification
- Running pytest should collect tests without syntax errors.
- `/api/v1/...` routes respond correctly.
- `/docs/api-reference.pdf` returns a valid PDF.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
