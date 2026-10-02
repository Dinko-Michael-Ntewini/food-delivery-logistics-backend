from typing import Annotated, Literal
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter,Depends,HTTPException,Query,Request,status
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,selectinload
from app.api.deps import get_current_active_user
from app.core.enums import UserRole,RestaurantStaffRole
from app.core.pagination import paginate, resolve_list_aliases, sorted_query
from app.db.session import get_db
from app.models.identity import User
from app.models.restaurant import Restaurant, RestaurantBranch, RestaurantStaff, Menu, Category, Product, ProductVariant
from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate, RestaurantOut, BranchCreate, BranchUpdate, BranchOut, StaffCreate, StaffUpdate, StaffOut, MenuCreate, MenuUpdate, MenuOut, CategoryCreate, CategoryUpdate, CategoryOut
from app.schemas.product import ProductCreate, ProductDirectCreate, ProductUpdate, ProductOut, VariantCreate, VariantUpdate, VariantOut, Page
from app.services.catalog import one,manage,commit,restaurant_for_menu,restaurant_for_category,restaurant_for_product
router=APIRouter()
DB=Annotated[Session,Depends(get_db)]; CU=Annotated[User,Depends(get_current_active_user)]
def active_owner_count(db,rid):
 return len(db.scalars(select(RestaurantStaff.id).where(RestaurantStaff.restaurant_id==rid,RestaurantStaff.branch_id.is_(None),RestaurantStaff.staff_role==RestaurantStaffRole.OWNER,RestaurantStaff.is_active.is_(True)).with_for_update()).all())
@router.post('/restaurants',response_model=RestaurantOut,status_code=201,tags=['Restaurants'])
def cr(x:RestaurantCreate,db:DB,u:CU):
 if u.role not in (UserRole.ADMIN,UserRole.RESTAURANT_OWNER):raise HTTPException(403)
 r=Restaurant(**x.model_dump());db.add(r)
 try:db.flush()
 except IntegrityError as exc:
  db.rollback()
  raise HTTPException(409,detail='Restaurant conflicts with an existing record') from exc
 if u.role==UserRole.RESTAURANT_OWNER:db.add(RestaurantStaff(restaurant_id=r.id,user_id=u.id,staff_role=RestaurantStaffRole.OWNER))
 return commit(db,r)
@router.get('/restaurants',response_model=Page[RestaurantOut],tags=['Restaurants'])
def lr(request:Request,db:DB,search:str|None=None,location:str|None=None,active:bool=True,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),sort:str=Query('name',pattern='^-?(name|created_at)$'),limit:int|None=Query(None,ge=1,le=100),sort_by:str|None=Query(None,pattern='^(name|created_at)$'),order:Literal['asc','desc']|None=None):
 page_size,sort=resolve_list_aliases(request,page_size,sort,limit=limit,sort_by=sort_by,order=order)
 q=select(Restaurant).where(Restaurant.is_active==active)
 if search:q=q.where(Restaurant.name.ilike(f'%{search}%'))
 if location:q=q.where(Restaurant.branches.any(RestaurantBranch.city.ilike(f'%{location}%')))
 return paginate(db,sorted_query(q,sort,{'name':Restaurant.name,'created_at':Restaurant.created_at},Restaurant.id),page,page_size)
@router.get('/restaurants/{rid}',response_model=RestaurantOut,tags=['Restaurants'])
def gr(rid:UUID,db:DB):return one(db,Restaurant,rid)
@router.patch('/restaurants/{rid}',response_model=RestaurantOut,tags=['Restaurants'])
def ur(rid:UUID,x:RestaurantUpdate,db:DB,u:CU):r=one(db,Restaurant,rid);manage(db,u,r.id);[setattr(r,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return commit(db,r)
@router.post('/restaurants/{rid}/branches',response_model=BranchOut,status_code=201,tags=['Branches'])
def cb(rid:UUID,x:BranchCreate,db:DB,u:CU):manage(db,u,rid);return commit(db,RestaurantBranch(restaurant_id=rid,**x.model_dump()))
@router.get('/restaurants/{rid}/branches',response_model=list[BranchOut],tags=['Branches'])
def lb(rid:UUID,db:DB):one(db,Restaurant,rid);return db.scalars(select(RestaurantBranch).where(RestaurantBranch.restaurant_id==rid,RestaurantBranch.is_active.is_(True))).all()
@router.get('/branches/{bid}',response_model=BranchOut,tags=['Branches'])
def gb(bid:UUID,db:DB):return one(db,RestaurantBranch,bid)
@router.patch('/branches/{bid}',response_model=BranchOut,tags=['Branches'])
def ub(bid:UUID,x:BranchUpdate,db:DB,u:CU):b=one(db,RestaurantBranch,bid);manage(db,u,b.restaurant_id);[setattr(b,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return commit(db,b)
@router.post('/restaurants/{rid}/staff',response_model=StaffOut,status_code=201,tags=['Restaurant Staff'])
def cs(rid:UUID,x:StaffCreate,db:DB,u:CU):
 manage(db,u,rid);target=one(db,User,x.user_id)
 if x.staff_role==RestaurantStaffRole.OWNER and (target.role!=UserRole.RESTAURANT_OWNER or x.branch_id is not None):raise HTTPException(422,detail='Owner membership requires a restaurant owner and no branch')
 if x.staff_role!=RestaurantStaffRole.OWNER and target.role!=UserRole.STAFF:raise HTTPException(422,detail='Staff membership requires a staff user')
 if x.branch_id and one(db,RestaurantBranch,x.branch_id).restaurant_id!=rid:raise HTTPException(422,detail='Branch does not belong to restaurant')
 if db.scalar(select(RestaurantStaff).where(RestaurantStaff.restaurant_id==rid,RestaurantStaff.user_id==x.user_id,RestaurantStaff.branch_id==x.branch_id)):raise HTTPException(409,detail='Duplicate membership')
 return commit(db,RestaurantStaff(restaurant_id=rid,**x.model_dump()))
@router.get('/restaurants/{rid}/staff',response_model=list[StaffOut],tags=['Restaurant Staff'])
def ls(rid:UUID,db:DB,u:CU):manage(db,u,rid);return db.scalars(select(RestaurantStaff).where(RestaurantStaff.restaurant_id==rid)).all()
@router.patch('/restaurants/{rid}/staff/{sid}',response_model=StaffOut,tags=['Restaurant Staff'])
def us(rid:UUID,sid:UUID,x:StaffUpdate,db:DB,u:CU):
 manage(db,u,rid);s=one(db,RestaurantStaff,sid)
 if s.restaurant_id!=rid:raise HTTPException(404,detail='Staff membership not found')
 d=x.model_dump(exclude_unset=True)
 if 'branch_id' in d and d['branch_id'] and one(db,RestaurantBranch,d['branch_id']).restaurant_id!=s.restaurant_id:raise HTTPException(422,detail='Branch does not belong to restaurant')
 if s.staff_role==RestaurantStaffRole.OWNER and s.is_active and (d.get('staff_role',s.staff_role)!=RestaurantStaffRole.OWNER or d.get('is_active',True) is False or d.get('branch_id',s.branch_id) is not None):
  if active_owner_count(db,rid)<=1:raise HTTPException(409,detail='Cannot remove final active owner')
 if d.get('staff_role',s.staff_role)==RestaurantStaffRole.OWNER and (s.user.role!=UserRole.RESTAURANT_OWNER or d.get('branch_id',s.branch_id) is not None):raise HTTPException(422,detail='Owner membership requires a restaurant owner and no branch')
 if d.get('staff_role',s.staff_role)!=RestaurantStaffRole.OWNER and s.user.role!=UserRole.STAFF:raise HTTPException(422,detail='Staff membership requires a staff user')
 for k,v in d.items():setattr(s,k,v)
 return commit(db,s)
@router.delete('/restaurants/{rid}/staff/{sid}',status_code=204,tags=['Restaurant Staff'])
def ds(rid:UUID,sid:UUID,db:DB,u:CU):
 manage(db,u,rid);s=one(db,RestaurantStaff,sid)
 if s.restaurant_id!=rid:raise HTTPException(404,detail='Staff membership not found')
 if s.staff_role==RestaurantStaffRole.OWNER and s.is_active and active_owner_count(db,rid)<=1:raise HTTPException(409,detail='Cannot remove final active owner')
 s.is_active=False;commit(db,s)
@router.post('/restaurants/{rid}/menus',response_model=MenuOut,status_code=201,tags=['Catalogue'])
def cm(rid:UUID,x:MenuCreate,db:DB,u:CU):manage(db,u,rid,catalogue=True);return commit(db,Menu(restaurant_id=rid,**x.model_dump()))
@router.get('/restaurants/{rid}/menus',response_model=list[MenuOut],tags=['Catalogue'])
def lm(rid:UUID,db:DB):one(db,Restaurant,rid);return db.scalars(select(Menu).where(Menu.restaurant_id==rid,Menu.is_active.is_(True))).all()
@router.get('/menus/{mid}',response_model=MenuOut,tags=['Catalogue'])
def gm(mid:UUID,db:DB):return one(db,Menu,mid)
@router.patch('/menus/{mid}',response_model=MenuOut,tags=['Catalogue'])
def um(mid:UUID,x:MenuUpdate,db:DB,u:CU):m=one(db,Menu,mid);manage(db,u,m.restaurant_id,catalogue=True);[setattr(m,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return commit(db,m)
@router.post('/menus/{mid}/categories',response_model=CategoryOut,status_code=201,tags=['Catalogue'])
def cc(mid:UUID,x:CategoryCreate,db:DB,u:CU):manage(db,u,restaurant_for_menu(db,mid),catalogue=True);return commit(db,Category(menu_id=mid,**x.model_dump()))
@router.get('/menus/{mid}/categories',response_model=list[CategoryOut],tags=['Catalogue'])
def lc(mid:UUID,db:DB):one(db,Menu,mid);return db.scalars(select(Category).where(Category.menu_id==mid,Category.is_active.is_(True))).all()
@router.get('/categories/{cid}',response_model=CategoryOut,tags=['Catalogue'])
def gc(cid:UUID,db:DB):return one(db,Category,cid)
@router.patch('/categories/{cid}',response_model=CategoryOut,tags=['Catalogue'])
def uc(cid:UUID,x:CategoryUpdate,db:DB,u:CU):c=one(db,Category,cid);manage(db,u,restaurant_for_category(db,cid),catalogue=True);[setattr(c,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return commit(db,c)
@router.post('/categories/{cid}/products',response_model=ProductOut,status_code=201,tags=['Products'])
def cp(cid:UUID,x:ProductCreate,db:DB,u:CU):manage(db,u,restaurant_for_category(db,cid),catalogue=True);return commit(db,Product(category_id=cid,**x.model_dump()))
@router.post('/products',response_model=ProductOut,status_code=201,tags=['Products'])
def cp_direct(x:ProductDirectCreate,db:DB,u:CU):
 manage(db,u,restaurant_for_category(db,x.category_id),catalogue=True)
 return commit(db,Product(**x.model_dump()))
@router.get('/products',response_model=Page[ProductOut],tags=['Products'])
@router.get('/products/search',response_model=Page[ProductOut],tags=['Products'])
def sp(request:Request,db:DB,search:str|None=None,category_id:UUID|None=None,restaurant_id:UUID|None=None,min_price:Decimal|None=Query(None,ge=0),max_price:Decimal|None=Query(None,ge=0),available:bool|None=True,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),sort:str=Query('name',pattern='^-?(name|price|created_at)$'),limit:int|None=Query(None,ge=1,le=100),sort_by:str|None=Query(None,pattern='^(name|price|created_at)$'),order:Literal['asc','desc']|None=None):
 page_size,sort=resolve_list_aliases(request,page_size,sort,limit=limit,sort_by=sort_by,order=order)
 if min_price is not None and max_price is not None and min_price>max_price:raise HTTPException(422,detail='min_price must not exceed max_price')
 q=select(Product).join(Category).join(Menu).join(Restaurant).where(Restaurant.is_active.is_(True),Menu.is_active.is_(True),Category.is_active.is_(True))
 if search:q=q.where(Product.name.ilike(f'%{search}%'))
 if category_id:q=q.where(Product.category_id==category_id)
 if restaurant_id:q=q.where(Menu.restaurant_id==restaurant_id)
 if min_price is not None:q=q.where(Product.base_price>=min_price)
 if max_price is not None:q=q.where(Product.base_price<=max_price)
 if available is not None:q=q.where(Product.is_available==available)
 return paginate(db,sorted_query(q,sort,{'price':Product.base_price,'name':Product.name,'created_at':Product.created_at},Product.id),page,page_size)
@router.get('/products/{pid}',response_model=ProductOut,tags=['Products'])
def gp(pid:UUID,db:DB):return one(db,Product,pid)
@router.patch('/products/{pid}',response_model=ProductOut,tags=['Products'])
def up(pid:UUID,x:ProductUpdate,db:DB,u:CU):p=one(db,Product,pid);manage(db,u,restaurant_for_product(db,pid),catalogue=True);[setattr(p,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return commit(db,p)
@router.post('/products/{pid}/variants',response_model=VariantOut,status_code=201,tags=['Products'])
def cv(pid:UUID,x:VariantCreate,db:DB,u:CU):manage(db,u,restaurant_for_product(db,pid),catalogue=True);return commit(db,ProductVariant(product_id=pid,**x.model_dump()))
@router.get('/products/{pid}/variants',response_model=list[VariantOut],tags=['Products'])
def lv(pid:UUID,db:DB):one(db,Product,pid);return db.scalars(select(ProductVariant).where(ProductVariant.product_id==pid,ProductVariant.is_available.is_(True))).all()
@router.patch('/variants/{vid}',response_model=VariantOut,tags=['Products'])
def uv(vid:UUID,x:VariantUpdate,db:DB,u:CU):
 v=one(db,ProductVariant,vid);manage(db,u,restaurant_for_product(db,v.product_id),catalogue=True);d=x.model_dump(exclude_unset=True)
 if d.get('price_override',v.price_override) is not None and d.get('price_delta',v.price_delta) is not None:raise HTTPException(422,detail='Only one price adjustment is allowed')
 [setattr(v,k,val) for k,val in d.items()];return commit(db,v)
