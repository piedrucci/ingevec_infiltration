from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session
from app.auth import require_admin
from app.db import get_db
from app.core.config import get_settings
from app.schemas import ExcelImportResponse
from app.services.excel_importer import import_workbook

imports_router=APIRouter(prefix='/imports',tags=['imports'])
@imports_router.post('/excel',response_model=ExcelImportResponse,status_code=status.HTTP_201_CREATED)
async def import_excel(file: UploadFile=File(...), _:dict=Depends(require_admin), db:Session=Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith('.xlsx'): raise HTTPException(415,'Only .xlsx files are accepted')
    content=await file.read()
    if len(content)>get_settings().MAX_EXCEL_SIZE_BYTES: raise HTTPException(413,'Excel file exceeds configured size limit')
    try:
        imported, created = import_workbook(db, content, file.filename)
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExcelImportResponse(import_id=imported.id,status=imported.status,row_count=imported.row_count,created=created)
