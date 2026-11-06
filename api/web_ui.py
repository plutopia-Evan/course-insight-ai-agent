"""Same-origin upload page; analysis and reports retain their Bearer protection."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from core.examples import sample_uploads


router = APIRouter(include_in_schema=False)
PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"


@router.get("/app")
def operator_page():
    return FileResponse(PAGE, media_type="text/html", headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    })


@router.get("/app/example")
def synthetic_example():
    return Response(sample_uploads()[0].data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Cache-Control": "public, max-age=3600"})
