from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import ERROR_RESPONSES, install_error_handlers
from app.api.auth import router as auth_router
from app.api.restaurants import router as restaurant_router
from app.api.customers import router as customer_router
from app.api.cart import router as cart_router
from app.api.orders import router as order_router
from app.api.payments import router as payment_router
from app.api.drivers import router as driver_router
from app.api.deliveries import router as delivery_router

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=False, responses=ERROR_RESPONSES)
install_error_handlers(app)
app.include_router(auth_router)
app.include_router(restaurant_router)
app.include_router(customer_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(payment_router)
app.include_router(driver_router)
app.include_router(delivery_router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "environment": settings.app_env}


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "healthy"}
