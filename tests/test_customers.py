from app.core.enums import UserRole
from app.core.security import create_access_token,hash_password
from app.models.identity import User
def mk(db,e,r):
 u=User(email=e,password_hash=hash_password('password123'),full_name=e,role=r,is_active=True);db.add(u);db.commit();db.refresh(u);return u
def h(u):return {'Authorization':f'Bearer {create_access_token(u.id)}'}
def test_profile_and_address_ownership(client,db_session):
 a=mk(db_session,'a@x.com',UserRole.CUSTOMER);b=mk(db_session,'b@x.com',UserRole.CUSTOMER);owner=mk(db_session,'o@x.com',UserRole.RESTAURANT_OWNER)
 assert client.get('/customers/me/profile').status_code==401
 assert client.get('/customers/me/profile',headers=h(owner)).status_code==403
 assert client.patch('/customers/me/profile',json={'marketing_opt_in':True},headers=h(a)).status_code==200
 x={'label':'Home','recipient_name':'A','recipient_phone':'1','line1':'One','city':'Accra','is_default':True}
 r=client.post('/customers/me/addresses',json=x,headers=h(a));assert r.status_code==201;aid=r.json()['id']
 x['label']='Work';x['line1']='Two';r2=client.post('/customers/me/addresses',json=x,headers=h(a));assert r2.status_code==201
 rows=client.get('/customers/me/addresses',headers=h(a)).json();assert sum(i['is_default'] for i in rows)==1
 assert client.get(f'/customers/me/addresses/{aid}',headers=h(b)).status_code==404
 assert client.patch(f'/customers/me/addresses/{aid}',json={'city':'Tema'},headers=h(b)).status_code==404
 assert client.delete(f'/customers/me/addresses/{aid}',headers=h(b)).status_code==404
 assert client.get('/customers/me/addresses/not-a-uuid',headers=h(a)).status_code==422
 assert client.delete(f"/customers/me/addresses/{r2.json()['id']}",headers=h(a)).status_code==204
