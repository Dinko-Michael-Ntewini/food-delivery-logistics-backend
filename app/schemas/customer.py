from uuid import UUID
from pydantic import BaseModel, Field
from app.core.enums import ContactMethod
from app.schemas.common import ORMModel
class ProfileUpdate(BaseModel): preferred_contact_method:ContactMethod|None=None; marketing_opt_in:bool|None=None
class ProfileOut(ORMModel): id:UUID; user_id:UUID; preferred_contact_method:ContactMethod|None; marketing_opt_in:bool
class AddressCreate(BaseModel):
 label:str=Field(min_length=1,max_length=60)
 recipient_name:str=Field(min_length=1,max_length=150)
 recipient_phone:str=Field(min_length=1,max_length=32)
 line1:str=Field(min_length=1,max_length=180)
 city:str=Field(min_length=1,max_length=100)
 line2:str|None=Field(default=None,max_length=180)
 landmark:str|None=Field(default=None,max_length=180)
 is_default:bool=False
class AddressUpdate(BaseModel):
 label:str|None=Field(default=None,min_length=1,max_length=60)
 recipient_name:str|None=Field(default=None,min_length=1,max_length=150)
 recipient_phone:str|None=Field(default=None,min_length=1,max_length=32)
 line1:str|None=Field(default=None,min_length=1,max_length=180)
 line2:str|None=Field(default=None,max_length=180)
 landmark:str|None=Field(default=None,max_length=180)
 city:str|None=Field(default=None,min_length=1,max_length=100)
 is_default:bool|None=None
class AddressOut(ORMModel): id:UUID; label:str; line1:str; city:str; is_default:bool
