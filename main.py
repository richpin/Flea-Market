import firebase_admin
import time
from firebase_admin import credentials, firestore, storage

from fastapi import FastAPI, Response, Request, Depends, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm

from fastapi_login import LoginManager
from fastapi_login.exceptions import InvalidCredentialsException
from pydantic import BaseModel

class User(BaseModel):
    username: str
    password: str
    nickname: str
    phone: str

SECRET = "secret"
manager = LoginManager(SECRET, '/login', use_cookie=True)

async def allow_guest(req: Request):
    try:
        manager.auto_error = True
        user = await manager(req)
        manager.auto_error = False
        return user
    except:
        return None

app = FastAPI()

app.mount("/img", StaticFiles(directory="img", html = True), name='img')
app.mount("/css", StaticFiles(directory="css", html = True), name='css')
templates = Jinja2Templates(directory="templates")

cred = credentials.Certificate("fleamarket-baab1-firebase-adminsdk-tifpm-a16fded8e3.json")
app_firebase = firebase_admin.initialize_app(cred)

db: firestore.firestore.Client = firestore.client() 
bucket = storage.bucket("fleamarket-baab1.appspot.com")

@app.post("/token")
def login(response: Response, data: OAuth2PasswordRequestForm = Depends()):
    username = data.username
    password = data.password
    
    query = db.collection('users').where('username', '==', username)\
        .where('password', '==', password)
    docs = query.get()

    if not docs:
        raise InvalidCredentialsException
    access_token = manager.create_access_token(
        data={'sub': username}
    )

    manager.set_cookie(response, access_token)
    return {'access_token': access_token}

@app.post("/register")
def register_user(response: Response, data: User):
    username = data.username

    new_data = {
        "nickname" : data.nickname,
        "phone" : data.phone,
        "username" : username,
        "password" : data.password,
        "wish" : list(),
        "cart" : list(),
        "sale"  : list(),
        "notices" : list()}

    user_ref = db.collection('users')\
                .document(username)
    if user_ref.get().exists:
        raise HTTPException(status_code=100)
    else: 
        user_ref.set(new_data)
    
    access_token = manager.create_access_token(
        data={'sub': username}
    )

    manager.set_cookie(response, access_token)

@app.get("/") 
def get_root(req: Request, user = Depends(allow_guest)):
    return templates.TemplateResponse("home.html", \
        {"request": req,
         "user": user,
         "populars": get_populars(),
         "recents": get_recents()})

@app.get("/admin") 
def get_root(req: Request, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    elif user['username'] == "admin":
        return templates.TemplateResponse("admin.html", \
            {"request": req,
            "user": user,
            "users": get_users()})
    else:
        return RedirectResponse(url='/')

def get_users():
    ref = db.collection('users')
    docs = ref.get()
    
    return [doc.to_dict() for doc in docs]

@app.get("/rmuser")
def remove_cart(id: str, user = Depends(allow_guest)):
    db.collection('users').document(id).delete()

    return RedirectResponse(url='/admin')

@app.get("/login")
def get_login():
    return FileResponse("login.html")

@app.get("/signup")
def get_signup():
    return FileResponse("sign_up.html")

@app.get("/logout")
def logout(response: Response):
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(key="access-token")
    return response

@app.get("/shop") 
def get_shop(req: Request, category: int, user = Depends(allow_guest)):
    if category == 0:
        category_str = "Electronics"
    elif category == 1:
        category_str = "Motors"
    elif category == 2:
        category_str = "Fashion"
    elif category == 3:
        category_str = "Book"
    elif category == 4:
        category_str = "Art"
    elif category == 5:
        category_str = "Sports"
    elif category == 6:
        category_str = "Health%Beauty"
    elif category == 7:
        category_str = "Home&Sports"
    else:
        category_str = "All"

    return templates.TemplateResponse("shop.html", \
        {"request": req,
         "user": user,
         "category": category_str,
         "products": get_category(category)})

@app.get("/search") 
def search(req: Request, search_by: str, search_content:str, user = Depends(allow_guest)):
    if search_by == "seller_name":
        products = get_by_seller(search_content)
    elif search_by == "product_name":
        products = get_by_name(search_content)
    elif search_by == "hoping_price":
        products = get_by_price(int(search_content))
    
    return templates.TemplateResponse("shop.html", \
        {"request": req,
         "user": user,
         "products": products})

@app.get("/cart")
def get_cart(req: Request, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    else:
        return templates.TemplateResponse("cart.html", \
            {"request": req,
            "user": user,
            "products": get_products(user['cart'])})

@app.get("/put_cart")
def put_cart(req: Request, id: str, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    else:
        ref = db.collection('users').document(user['username'])
        ref.update({'cart': firestore.ArrayUnion([id])})
        return RedirectResponse(url='cart')

@app.get("/rmcart")
def remove_cart(id: str, user = Depends(allow_guest)):
    ref = db.collection('users').document(user['username'])
    ref.update({'cart':firestore.ArrayRemove([id])})

    return RedirectResponse(url='/cart')

@app.get("/wish")
def get_cart(req: Request, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    else:
        return templates.TemplateResponse("wish.html", \
            {"request": req,
            "user": user,
            "products": get_products(user['wish'])})

@app.get("/put_wish")
def put_wish(req: Request, id: str, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    else:
        ref_user = db.collection('users').document(user['username'])
        ref_user.update({'wish': firestore.ArrayUnion([id])})
        ref_product = db.collection('products').document(id)
        ref_product.update({'wish_cnt': firestore.Increment(1)})
        return RedirectResponse(url='/wish')

@app.get("/rmwish")
def remove_wish(id: str, user = Depends(allow_guest)):
    ref = db.collection('users').document(user['username'])
    ref.update({'wish':firestore.ArrayRemove([id])})

    return RedirectResponse(url='/wish')

@app.post("/upload")
def upload_product(image: UploadFile, category: str = Form(), name: str = Form(), price: str = Form(), trading: str = Form(), description: str = Form(), user = Depends(allow_guest)):
    blob = bucket.blob(image.filename)
    blob.upload_from_file(image.file)
    blob.make_public()
    
    data = {
        "image" : blob.public_url,
        "category" : int(category),
        "name" : name,
        "price" : int(price),
        "place" : trading,
        "description" : description,
        "seller" : user['nickname'],
        "phone" : user['phone'],
        "date" : int(time.time()),
        "wish_cnt" : 0,
        "auction" : True,
        "recent_bid" : ""
    }   

    ref = db.collection('products').document()
    data["id"] = ref.id
    ref.set(data)

    db.collection('users').document(user['username'])\
        .update({'sale' : firestore.ArrayUnion([ref.id])})

@app.get("/notification")
def get_notice(req: Request, user = Depends(allow_guest)):
    return templates.TemplateResponse("notification.html", \
        {"request": req,
        "user" : user,
        "products": get_products(user['notices'])})

@app.get("/sale")
def get_cart(req: Request, user = Depends(allow_guest)):
    if user is None:
        return RedirectResponse(url='/login')
    else:
        return templates.TemplateResponse("sale.html", \
            {"request": req,
            "user": user,
            "products": get_products(user['sale'])})

@app.get("/detail")
def get_detail(req: Request, id: str, user = Depends(allow_guest)):
    product = db.collection('products').document(id).get().to_dict()

    return templates.TemplateResponse("detail.html", \
            {"request": req,
            "user": user,
            "product": product})

@app.get("/sell")
def get_detail(req: Request, user = Depends(allow_guest)):
    return templates.TemplateResponse("sell.html", \
            {"request": req,
            "user": user})

class ID(BaseModel):
    id: str
    price: str

@app.post("/stopbid")
def stop_bid(response: Response, ID: ID):
    db.collection('products').document(ID.id).update({'auction': False})

@app.post("/bid")
def add_bid(response: Response, ID: ID, user = Depends(allow_guest)):
    ref = db.collection('products').document(ID.id)
    ref.update({'price': int(ID.price)})

    product = ref.get().to_dict()
    if product['recent_bid'] != "":
        db.collection('users').document(product['recent_bid'])\
            .update({'notices': firestore.ArrayUnion([product['id']])})

    ref.update({'recent_bid': user['username']})

@manager.user_loader()
def get_user(username: str):
    query = db.collection('users').where('username', '==', username)
    docs = query.get()
  
    return docs[0].to_dict()

def get_populars():
    query = db.collection('products').order_by('wish_cnt', direction=firestore.Query.DESCENDING).limit(8)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]
    
def get_recents():
    query = db.collection('products').order_by('date', direction=firestore.Query.DESCENDING).limit(8)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]

def get_category(category: int):
    if category == 10:
        query = db.collection('products')
    else:
        query = db.collection('products').where('category', '==', category)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]

def get_products(cart: list):
    carts = list()

    for c in cart:
        carts.append(db.collection('products').document(c).get().to_dict())

    return carts

def get_by_seller(name: str):
    query = db.collection('products').where('seller', '==', name)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]

def get_by_name(name: str):
    query = db.collection('products').where('name', '==', name)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]

def get_by_price(price: int):
    query = db.collection('products').where('price', '<=', price)
    docs = query.get()
    
    return [doc.to_dict() for doc in docs]