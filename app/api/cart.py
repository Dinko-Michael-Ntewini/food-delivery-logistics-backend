from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.identity import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartOut
from app.services.cart import current_cart, cart_response, add_item, update_item, remove_item

router = APIRouter(prefix="/cart", tags=["Cart"])
DB = Annotated[Session, Depends(get_db)]
CU = Annotated[User, Depends(get_current_active_user)]


@router.get("", response_model=CartOut)
def get_cart(db: DB, user: CU) -> CartOut:
    return cart_response(db, current_cart(db, user))


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def post_cart_item(data: CartItemCreate, db: DB, user: CU) -> CartOut:
    return add_item(db, user, data)


@router.patch("/items/{cart_item_id}", response_model=CartOut)
def patch_cart_item(cart_item_id: UUID, data: CartItemUpdate, db: DB, user: CU) -> CartOut:
    return update_item(db, user, cart_item_id, data.quantity)


@router.delete("/items/{cart_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(cart_item_id: UUID, db: DB, user: CU) -> None:
    remove_item(db, user, cart_item_id)
