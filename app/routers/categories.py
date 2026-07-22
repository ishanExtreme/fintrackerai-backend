from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db
from ..utils import descendant_category_ids

router = APIRouter(prefix="/categories", tags=["categories"])


def _get_owned_category(db: Session, user_id: int, category_id: int) -> models.Category:
    cat = (
        db.query(models.Category)
        .filter(models.Category.id == category_id, models.Category.user_id == user_id)
        .first()
    )
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return cat


@router.post("", response_model=schemas.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if payload.parent_id is not None:
        _get_owned_category(db, user.id, payload.parent_id)

    cat = models.Category(
        user_id=user.id,
        name=payload.name,
        parent_id=payload.parent_id,
        description=payload.description,
        image=payload.image,
        type=payload.type,
        tags=payload.tags or [],
        created_by=payload.created_by if payload.created_by in {"user", "llm"} else "user",
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("", response_model=list[schemas.CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Category)
        .filter(models.Category.user_id == user.id)
        .order_by(models.Category.name)
        .all()
    )


@router.get("/tree", response_model=list[schemas.CategoryTree])
def category_tree(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cats = (
        db.query(models.Category)
        .filter(models.Category.user_id == user.id)
        .order_by(models.Category.name)
        .all()
    )
    nodes: dict[int, schemas.CategoryTree] = {
        c.id: schemas.CategoryTree.model_validate(c) for c in cats
    }
    roots: list[schemas.CategoryTree] = []
    for c in cats:
        node = nodes[c.id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


@router.patch("/{category_id}", response_model=schemas.CategoryOut)
def update_category(
    category_id: int,
    payload: schemas.CategoryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cat = _get_owned_category(db, user.id, category_id)

    data = payload.model_dump(exclude_unset=True)

    # Reparenting (drag-and-drop): validate ownership and guard against cycles.
    # A null parent_id detaches the category to the top level.
    if "parent_id" in data and data["parent_id"] is not None:
        new_parent_id = data["parent_id"]
        if new_parent_id == category_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A category cannot be its own parent")
        _get_owned_category(db, user.id, new_parent_id)
        if new_parent_id in descendant_category_ids(db, user.id, category_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cannot move a category under one of its own descendants",
            )

    for field, value in data.items():
        setattr(cat, field, value)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cat = _get_owned_category(db, user.id, category_id)
    # ORM cascade handles children; detach transactions (they become uncategorised).
    db.query(models.Transaction).filter(
        models.Transaction.user_id == user.id,
        models.Transaction.category_id == category_id,
    ).update({models.Transaction.category_id: None})
    db.delete(cat)
    db.commit()
    return None
