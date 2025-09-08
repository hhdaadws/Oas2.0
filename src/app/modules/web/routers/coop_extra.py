"""
勾协库额外操作（批量删除）
"""
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....db.base import get_db
from ....db.models import CoopAccount


router = APIRouter(prefix="/api/coop", tags=["coop"])


class CoopBatchDelete(BaseModel):
    ids: List[int]


@router.post("/accounts/batch-delete")
async def batch_delete_accounts(data: CoopBatchDelete, db: Session = Depends(get_db)):
    ids = [int(i) for i in (data.ids or [])]
    if not ids:
        return {"success": True, "deleted": 0}
    deleted = db.query(CoopAccount).filter(CoopAccount.id.in_(ids)).delete(
        synchronize_session=False
    )
    db.commit()
    return {"success": True, "deleted": deleted}

