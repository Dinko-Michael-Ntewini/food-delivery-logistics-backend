from typing import Annotated
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_active_user
from app.core.enums import UserRole
from app.db.session import get_db
from app.models.identity import Address,User
from app.models.ordering import Order
from app.schemas.customer import ProfileUpdate, ProfileOut, AddressCreate, AddressUpdate, AddressOut
from app.services.customers import profile,address,set_default
router=APIRouter(prefix='/customers/me')
DB=Annotated[Session,Depends(get_db)]; CU=Annotated[User,Depends(get_current_active_user)]
def customer(u):
 if u.role!=UserRole.CUSTOMER:raise HTTPException(403,detail='Customer access required')
def save(db,entity):
 try: db.commit()
 except IntegrityError as exc:
  db.rollback()
  raise HTTPException(409,detail='Address or profile conflicts with a database constraint') from exc
 db.refresh(entity)
 return entity
@router.get('/profile',response_model=ProfileOut,tags=['Customers'])
def get_profile(db:DB,u:CU):customer(u);return profile(db,u)
@router.patch('/profile',response_model=ProfileOut,tags=['Customers'])
def update_profile(x:ProfileUpdate,db:DB,u:CU):
 customer(u);p=profile(db,u);[setattr(p,k,v) for k,v in x.model_dump(exclude_unset=True).items()];return save(db,p)
@router.post('/addresses',response_model=AddressOut,status_code=201,tags=['Addresses'])
def create_address(x:AddressCreate,db:DB,u:CU):
 customer(u);a=Address(user_id=u.id,**x.model_dump());set_default(db,u,a);db.add(a);return save(db,a)
@router.get('/addresses',response_model=list[AddressOut],tags=['Addresses'])
def list_addresses(db:DB,u:CU):customer(u);return db.scalars(select(Address).where(Address.user_id==u.id)).all()
@router.get('/addresses/{aid}',response_model=AddressOut,tags=['Addresses'])
def get_address(aid:UUID,db:DB,u:CU):customer(u);return address(db,u,aid)
@router.patch('/addresses/{aid}',response_model=AddressOut,tags=['Addresses'])
def update_address(aid:UUID,x:AddressUpdate,db:DB,u:CU):
 customer(u);a=address(db,u,aid);[setattr(a,k,v) for k,v in x.model_dump(exclude_unset=True).items()];set_default(db,u,a);return save(db,a)
@router.delete('/addresses/{aid}',status_code=204,tags=['Addresses'])
def delete_address(aid:UUID,db:DB,u:CU):
 customer(u);a=address(db,u,aid)
 if db.scalar(select(Order.id).where(Order.delivery_address_id==a.id).limit(1)) is not None:raise HTTPException(409,detail='Address is referenced by an Order')
 db.delete(a)
 try:db.commit()
 except IntegrityError as exc:
  db.rollback()
  raise HTTPException(409,detail='Address is referenced by another record') from exc
