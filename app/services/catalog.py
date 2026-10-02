from uuid import UUID
from fastapi import HTTPException
from app.core.exceptions import ConflictError, NotFoundError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.enums import UserRole, RestaurantStaffRole
from app.models.restaurant import Restaurant, RestaurantStaff, Menu, Category, Product, ProductVariant
def one(db, cls, ident):
 try: ident=UUID(str(ident))
 except ValueError: raise HTTPException(404,detail=f"{cls.__name__} not found")
 o=db.get(cls,ident)
 if not o: raise NotFoundError(f"{cls.__name__} not found")
 return o
def manage(db,user,restaurant_id,*,catalogue=False):
 try: restaurant_id=UUID(str(restaurant_id))
 except ValueError: raise HTTPException(404,detail="Restaurant not found")
 one(db,Restaurant,restaurant_id)
 if user.role==UserRole.ADMIN:return
 membership=db.scalar(select(RestaurantStaff).where(RestaurantStaff.restaurant_id==restaurant_id,RestaurantStaff.user_id==user.id,RestaurantStaff.branch_id.is_(None),RestaurantStaff.is_active.is_(True)))
 owner=user.role==UserRole.RESTAURANT_OWNER and membership and membership.staff_role==RestaurantStaffRole.OWNER
 manager=catalogue and user.role==UserRole.STAFF and membership and membership.staff_role==RestaurantStaffRole.MANAGER
 if not (owner or manager):raise HTTPException(403,detail="Restaurant access denied")
def restaurant_for_menu(db,menu_id): return one(db,Menu,menu_id).restaurant_id
def restaurant_for_category(db,category_id): return one(db,Category,category_id).menu.restaurant_id
def restaurant_for_product(db,product_id): return one(db,Product,product_id).category.menu.restaurant_id
def commit(db,o):
 db.add(o)
 try: db.commit()
 except IntegrityError as exc:
  db.rollback()
  raise ConflictError("Resource conflicts with an existing record or database constraint") from exc
 db.refresh(o); return o
