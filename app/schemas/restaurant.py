from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field
from app.core.enums import RestaurantStaffRole
from app.schemas.common import ORMModel

class RestaurantCreate(BaseModel): name:str=Field(min_length=1,max_length=160); slug:str=Field(min_length=1,max_length=180); contact_email:str|None=None; contact_phone:str|None=None; description:str|None=None
class RestaurantUpdate(BaseModel): name:str|None=None; contact_email:str|None=None; contact_phone:str|None=None; description:str|None=None; is_active:bool|None=None
class RestaurantOut(ORMModel): id:UUID; name:str; slug:str; description:str|None; is_active:bool
class BranchCreate(BaseModel): name:str; line1:str; city:str; phone:str|None=None; email:str|None=None; latitude:Decimal|None=None; longitude:Decimal|None=None
class BranchUpdate(BaseModel): name:str|None=None; line1:str|None=None; city:str|None=None; is_active:bool|None=None
class BranchOut(ORMModel): id:UUID; restaurant_id:UUID; name:str; line1:str; city:str; is_active:bool
class StaffCreate(BaseModel): user_id:UUID; branch_id:UUID|None=None; staff_role:RestaurantStaffRole=RestaurantStaffRole.STAFF
class StaffUpdate(BaseModel): branch_id:UUID|None=None; staff_role:RestaurantStaffRole|None=None; is_active:bool|None=None
class StaffOut(ORMModel): id:UUID; restaurant_id:UUID; user_id:UUID; branch_id:UUID|None; staff_role:RestaurantStaffRole; is_active:bool
class MenuCreate(BaseModel): name:str; description:str|None=None
class MenuUpdate(BaseModel): name:str|None=None; description:str|None=None; is_active:bool|None=None
class MenuOut(ORMModel): id:UUID; restaurant_id:UUID; name:str; description:str|None; is_active:bool
class CategoryCreate(BaseModel): name:str; description:str|None=None; display_order:int=0
class CategoryUpdate(BaseModel): name:str|None=None; description:str|None=None; display_order:int|None=None; is_active:bool|None=None
class CategoryOut(ORMModel): id:UUID; menu_id:UUID; name:str; description:str|None; display_order:int; is_active:bool
