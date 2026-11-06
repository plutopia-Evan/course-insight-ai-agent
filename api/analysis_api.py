"""Upload once, then retrieve the existing analysis by its stable ID."""

import math
from datetime import datetime, date

import numpy as np
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from api.analysis_runner import analyze_upload
from core.analysis_results import analysis_payload, load_analysis_result


router = APIRouter(tags=["analysis"])


def convert_numpy(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        value = float(obj)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(obj, np.ndarray):
        return [convert_numpy(x) for x in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return [convert_numpy(row) for row in obj.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return [convert_numpy(x) for x in obj.tolist()]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: convert_numpy(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [convert_numpy(value) for value in obj]
    return obj


@router.post("/analysis")
async def analysis(file: UploadFile = File(...)):
    result = await analyze_upload(file)
    response = {
        **analysis_payload(result),
        "normalized_long": result.get("df_long", []),
        "anomalies": result.get("anomalies", []),
    }
    return JSONResponse(content=convert_numpy(response))


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    """Return stored counts, feedback and download URL without new model calls."""
    try:
        return load_analysis_result(analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
