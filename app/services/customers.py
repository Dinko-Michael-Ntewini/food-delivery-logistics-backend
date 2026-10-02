from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.identity import CustomerProfile,Address
def profile(db,user):
 p=db.scalar(select(CustomerProfile).where(CustomerProfile.user_id==user.id))
 if not p:
  p=CustomerProfile(user_id=user.id);db.add(p)
  try:db.commit();db.refresh(p)
  except IntegrityError:
   db.rollback()
   p=db.scalar(select(CustomerProfile).where(CustomerProfile.user_id==user.id))
   if p is None:raise HTTPException(409,detail='Customer profile creation conflict')
 return p
def address(db,user,ident):
 a=db.get(Address,ident)
 if not a or a.user_id!=user.id:raise HTTPException(404,detail='Address not found')
 return a
def set_default(db,user,a):
 if a.is_default:
  a.is_default=False
  with db.no_autoflush:
   previous=db.scalars(select(Address).where(Address.user_id==user.id,Address.is_default.is_(True))).all()
  for old in previous:
   if old is not a: old.is_default=False
  if any(old is not a for old in previous): db.flush()
  a.is_default=True
