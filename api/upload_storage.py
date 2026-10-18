"""Store one request's survey file in an isolated, short-lived directory."""

from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException, UploadFile

from api.request_limits import MAX_UPLOAD_BYTES


@asynccontextmanager
async def saved_upload(file: UploadFile):
    filename = file.filename or ""
    if (not filename or filename in {".", ".."}
            or any(char in filename for char in "/\\:\x00")
            or Path(filename).suffix.lower() != ".xlsx"):
        raise HTTPException(status_code=400, detail="请上传文件名有效的 .xlsx 问卷")

    upload_dir = Path("data/upload")
    upload_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="survey-", dir=upload_dir) as directory:
        path = Path(directory) / filename
        try:
            with path.open("wb") as output:
                total_bytes = 0
                while chunk := await file.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="问卷文件不能超过 10 MB",
                        )
                    output.write(chunk)
            yield path
        finally:
            await file.close()
