from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import CartStatus, UserRole
from app.models.identity import CustomerProfile, User
from app.models.ordering import Cart, CartItem
from app.models.restaurant import Product, ProductVariant, RestaurantBranch
from app.schemas.cart import CartItemCreate, CartItemOut, CartOut


def require_customer(user: User) -> None:
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(403, detail="Customer access required")


def current_cart(db: Session, user: User) -> Cart:
    require_customer(user)
    profile = db.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
    if profile is None:
        profile = CustomerProfile(user_id=user.id)
        db.add(profile)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            profile = db.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
            if profile is None:
                raise HTTPException(409, detail="Customer profile creation conflict")
    cart = db.scalar(select(Cart).where(Cart.customer_id == profile.id, Cart.status == CartStatus.ACTIVE))
    if cart is None:
        cart = Cart(customer_id=profile.id, branch_id=None, status=CartStatus.ACTIVE)
        db.add(cart)
        try:
            db.commit()
            db.refresh(cart)
        except IntegrityError:
            db.rollback()
            cart = db.scalar(select(Cart).where(Cart.customer_id == profile.id, Cart.status == CartStatus.ACTIVE))
            if cart is None:
                raise HTTPException(409, detail="Active cart creation conflict")
    return cart


def unit_price(product: Product, variant: ProductVariant | None) -> Decimal:
    base = product.base_price
    if variant is None:
        return base
    if variant.price_override is not None:
        return variant.price_override
    return base + (variant.price_delta if variant.price_delta is not None else Decimal("0.00"))


def cart_response(db: Session, cart: Cart) -> CartOut:
    rows = db.scalars(select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.created_at, CartItem.id)).all()
    result: list[CartItemOut] = []
    subtotal = Decimal("0.00")
    for row in rows:
        product = row.product
        variant = row.product_variant
        price = unit_price(product, variant)
        line = price * row.quantity
        subtotal += line
        result.append(CartItemOut(id=row.id, product_id=product.id, product_name=product.name,
                                  product_variant_id=variant.id if variant else None,
                                  variant_name=variant.name if variant else None, quantity=row.quantity,
                                  unit_price=price, line_total=line,
                                  product_available=product.is_available and product.category.is_active and product.category.menu.is_active and product.category.menu.restaurant.is_active,
                                  variant_available=variant.is_available if variant else None))
    branch = db.get(RestaurantBranch, cart.branch_id) if cart.branch_id else None
    return CartOut(id=cart.id, branch_id=cart.branch_id,
                   restaurant_id=branch.restaurant_id if branch else None,
                   items=result, subtotal=subtotal)


def add_item(db: Session, user: User, data: CartItemCreate) -> CartOut:
    cart = current_cart(db, user)
    db.execute(select(Cart.id).where(Cart.id == cart.id).with_for_update()).first()
    product = db.get(Product, data.product_id)
    if product is None:
        raise HTTPException(404, detail="Product not found")
    restaurant = product.category.menu.restaurant
    if not (product.is_available and product.category.is_active and product.category.menu.is_active and restaurant.is_active):
        raise HTTPException(409, detail="Product unavailable")
    variant = None
    if data.product_variant_id is not None:
        variant = db.get(ProductVariant, data.product_variant_id)
        if variant is None:
            raise HTTPException(404, detail="Variant not found")
        if variant.product_id != product.id:
            raise HTTPException(422, detail="Variant does not belong to product")
        if not variant.is_available:
            raise HTTPException(409, detail="Variant unavailable")
    has_items = db.scalar(select(CartItem.id).where(CartItem.cart_id == cart.id).limit(1)) is not None
    if not has_items:
        if data.branch_id is None:
            raise HTTPException(422, detail="branch_id is required for the first item")
        branch = db.get(RestaurantBranch, data.branch_id)
        if branch is None:
            raise HTTPException(404, detail="Branch not found")
        if not branch.is_active:
            raise HTTPException(409, detail="Branch unavailable")
        if branch.restaurant_id != restaurant.id:
            raise HTTPException(409, detail="Branch and product belong to different restaurants")
        cart.branch_id = branch.id
    else:
        if data.branch_id is not None and data.branch_id != cart.branch_id:
            raise HTTPException(409, detail="Cart is scoped to another branch")
        branch = db.get(RestaurantBranch, cart.branch_id)
        if branch is None or not branch.is_active:
            raise HTTPException(409, detail="Cart branch unavailable")
        if branch.restaurant_id != restaurant.id:
            raise HTTPException(409, detail="Cart is scoped to another restaurant")
    existing = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id,
                                                 CartItem.product_id == product.id,
                                                 CartItem.product_variant_id == data.product_variant_id))
    if existing is None:
        db.add(CartItem(cart_id=cart.id, product_id=product.id,
                        product_variant_id=data.product_variant_id, quantity=data.quantity))
    else:
        existing.quantity += data.quantity
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        competing = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id,
                                                     CartItem.product_id == data.product_id,
                                                     CartItem.product_variant_id == data.product_variant_id))
        if competing is None:
            raise HTTPException(409, detail="Cart item changed concurrently; retry the request") from exc
        if data.branch_id is not None and cart.branch_id != data.branch_id:
            raise HTTPException(409, detail="Cart is scoped to another branch") from exc
        competing.quantity += data.quantity
        try:
            db.commit()
        except IntegrityError as retry_exc:
            db.rollback()
            raise HTTPException(409, detail="Cart item changed concurrently; retry the request") from retry_exc
    return cart_response(db, cart)


def own_item(db: Session, cart: Cart, item_id: UUID) -> CartItem:
    item = db.get(CartItem, item_id)
    if item is None or item.cart_id != cart.id:
        raise HTTPException(404, detail="Cart item not found")
    return item


def update_item(db: Session, user: User, item_id: UUID, quantity: int) -> CartOut:
    cart = current_cart(db, user)
    item = own_item(db, cart, item_id)
    item.quantity = quantity
    db.commit()
    return cart_response(db, cart)


def remove_item(db: Session, user: User, item_id: UUID) -> None:
    cart = current_cart(db, user)
    item = own_item(db, cart, item_id)
    db.delete(item)
    db.flush()
    if db.scalar(select(CartItem.id).where(CartItem.cart_id == cart.id).limit(1)) is None:
        cart.branch_id = None
    db.commit()
