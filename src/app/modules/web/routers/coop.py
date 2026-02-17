"""
勾协库管理 API
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....db.base import get_db
from ....db.models import CoopAccount, CoopWindow


router = APIRouter(prefix="/api/coop", tags=["coop"])


def _current_window(now: Optional[datetime] = None) -> (str, int):
    """计算当前时间所在窗口 (window_date, slot)。
    规则：
      - now < 当日12:00      → (昨日, 18)
      - 12:00 ≤ now < 18:00  → (今日, 12)
      - now ≥ 18:00          → (今日, 18)
    返回 window_date 为 YYYY-MM-DD 字符串。
    """
    now = now or datetime.now()
    today = now.date()
    noon = datetime.combine(today, datetime.min.time()).replace(hour=12)
    eve = datetime.combine(today, datetime.min.time()).replace(hour=18)
    if now < noon:
        wd = (today - timedelta(days=1)).isoformat()
        return wd, 18
    elif now < eve:
        return today.isoformat(), 12
    else:
        return today.isoformat(), 18


class CoopAccountCreate(BaseModel):
    login_id: str
    expire_date: Optional[str] = None  # YYYY-MM-DD
    note: Optional[str] = None


class CoopAccountUpdate(BaseModel):
    status: Optional[int] = None  # 1|2
    expire_date: Optional[str] = None
    note: Optional[str] = None


@router.get("/accounts")
async def list_coop_accounts(
    status: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    expiry: Optional[str] = Query(None, description="valid|expired|all"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(CoopAccount)
    if status:
        query = query.filter(CoopAccount.status == status)
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(CoopAccount.login_id.like(kw))

    # 过期筛选
    if expiry in ("valid", "expired"):
        today = datetime.now().date()
        # SQLite 无法直接按日期比较字符串可靠，这里在应用层过滤
        all_items: List[CoopAccount] = query.all()
        def is_expired(acc: CoopAccount) -> bool:
            if not acc.expire_date:
                return False
            try:
                d = datetime.strptime(acc.expire_date, "%Y-%m-%d").date()
                return d < today
            except Exception:
                return False
        if expiry == "valid":
            items = [a for a in all_items if not is_expired(a)]
        else:
            items = [a for a in all_items if is_expired(a)]
        total = len(items)
        accounts = items[offset: offset + limit]
    else:
        total = query.count()
        accounts = query.order_by(CoopAccount.created_at.desc()).limit(limit).offset(offset).all()

    # 取当前窗口用量
    wd, slot = _current_window()
    ids = [a.id for a in accounts]
    win_map: Dict[int, CoopWindow] = {}
    if ids:
        wins = (
            db.query(CoopWindow)
            .filter(
                CoopWindow.coop_account_id.in_(ids),
                CoopWindow.window_date == wd,
                CoopWindow.slot == slot,
            )
            .all()
        )
        win_map = {w.coop_account_id: w for w in wins}

    result = []
    today = datetime.now().date()
    for a in accounts:
        w = win_map.get(a.id)
        used = w.used_count if w else 0
        completed = used >= 2
        # 过期判定
        expired_flag = False
        if a.expire_date:
            try:
                d = datetime.strptime(a.expire_date, "%Y-%m-%d").date()
                expired_flag = d < today
            except Exception:
                expired_flag = False
        result.append(
            {
                "id": a.id,
                "login_id": a.login_id,
                "status": a.status,
                "expire_date": a.expire_date,
                "note": a.note,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "expired": expired_flag,
                "window": {"date": wd, "slot": slot, "used": used, "capacity": 2, "completed": completed},
            }
        )

    return {"total": total, "limit": limit, "offset": offset, "accounts": result}


@router.post("/accounts")
async def create_coop_account(data: CoopAccountCreate, db: Session = Depends(get_db)):
    login_id = (data.login_id or "").strip()
    if not login_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="login_id 不能为空")
    existed = db.query(CoopAccount).filter(CoopAccount.login_id == login_id).first()
    if existed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录ID已存在")
    # 校验过期日期
    expire_date = None
    if data.expire_date:
        try:
            datetime.strptime(data.expire_date, "%Y-%m-%d")
            expire_date = data.expire_date
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="过期日期格式应为 YYYY-MM-DD")
    obj = CoopAccount(login_id=login_id, note=data.note, status=1, expire_date=expire_date)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "login_id": obj.login_id}


@router.put("/accounts/{account_id}")
async def update_coop_account(account_id: int, data: CoopAccountUpdate, db: Session = Depends(get_db)):
    obj = db.query(CoopAccount).filter(CoopAccount.id == account_id).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="勾协账号不存在")
    if data.status is not None:
        obj.status = int(data.status)
    if data.expire_date is not None:
        if data.expire_date == "":
            obj.expire_date = None
        else:
            try:
                datetime.strptime(data.expire_date, "%Y-%m-%d")
                obj.expire_date = data.expire_date
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="过期日期格式应为 YYYY-MM-DD")
    if data.note is not None:
        obj.note = data.note
    obj.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.delete("/accounts/{account_id}")
async def delete_coop_account(account_id: int, db: Session = Depends(get_db)):
    obj = db.query(CoopAccount).filter(CoopAccount.id == account_id).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="勾协账号不存在")
    db.delete(obj)
    db.commit()
    return {"success": True}

# 按当前需求：不提供批量导入接口
