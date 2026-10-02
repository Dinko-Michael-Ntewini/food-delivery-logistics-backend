from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from app.schemas.common import ORMModel, Page
class ProductCreate(BaseModel): name:str=Field(min_length=1,max_length=160); description:str|None=None; base_price:Decimal=Field(ge=0,max_digits=12,decimal_places=2); image_url:str|None=Field(default=None,max_length=2048)
class ProductDirectCreate(ProductCreate): category_id:UUID
class ProductUpdate(BaseModel): name:str|None=Field(default=None,min_length=1,max_length=160); description:str|None=None; base_price:Decimal|None=Field(default=None,ge=0,max_digits=12,decimal_places=2); is_available:bool|None=None; image_url:str|None=Field(default=None,max_length=2048)
class ProductOut(ORMModel): id:UUID; category_id:UUID; name:str; description:str|None; base_price:Decimal; is_available:bool; image_url:str|None
class VariantCreate(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 sku:str|None=Field(default=None,max_length=80)
 price_override:Decimal|None=Field(default=None,ge=0,decimal_places=2,max_digits=12)
 price_delta:Decimal|None=Field(default=None,ge=0,decimal_places=2,max_digits=12)
 @model_validator(mode='after')
 def one_adjustment(self):
  if self.price_override is not None and self.price_delta is not None:raise ValueError('Only one price adjustment is allowed')
  return self
class VariantUpdate(BaseModel):
 name:str|None=Field(default=None,min_length=1,max_length=120)
 sku:str|None=Field(default=None,max_length=80)
 price_override:Decimal|None=Field(default=None,ge=0,decimal_places=2,max_digits=12)
 price_delta:Decimal|None=Field(default=None,ge=0,decimal_places=2,max_digits=12)
 is_available:bool|None=None
class VariantOut(ORMModel): id:UUID; product_id:UUID; name:str; sku:str|None; price_override:Decimal|None; price_delta:Decimal|None; is_available:bool
