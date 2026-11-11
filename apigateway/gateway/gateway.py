import os
import httpx
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Response
)
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

app = FastAPI(title="Fit Express - Production API Gateway")

security = HTTPBearer(auto_error=False)

# Direcciones de Servicios
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8100")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "root-dev-token")

# Mapeo de microservicios internos del dominio (Módulo 3)
SERVICES_ROUTING = {
    "inventory": os.getenv("INVENTORY_SERVICE_URL", "http://127.0.0.1:9001"),
    "orders": os.getenv("ORDERS_SERVICE_URL", "http://127.0.0.1:9001"),
    "clients": os.getenv("CLIENTS_SERVICE_URL", "http://127.0.0.1:9001"),
    "payments": os.getenv("PAYMENTS_SERVICE_URL", "http://127.0.0.1:9001"),
    "dispatch": os.getenv("DISPATCH_SERVICE_URL", "http://127.0.0.1:9001"),
    "reports": os.getenv("REPORTS_SERVICE_URL", "http://127.0.0.1:9001"),
    "graphql": os.getenv("GRAPHQL_GATEWAY_URL", "http://127.0.0.1:8090")
}

# Obtener secretos de Vault con fallback local seguro (Módulo 6)
async def get_gateway_secrets():
    url = f"{VAULT_ADDR}/v1/secret/data/gateway"
    headers = {"X-Vault-Token": VAULT_TOKEN}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()["data"]["data"]
    except Exception:
        pass

    return {
        "auth_introspection_secret": os.getenv("AUTH_INTROSPECTION_SECRET", "fit_intro_secret_2026"),
        "backend_shared_secret": os.getenv("BACKEND_SHARED_SECRET", "fit_shared_secret_2026")
    }

# Autenticación e introspección mediante AuthService (Módulos 4 y 5)
async def authenticate_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    path = request.url.path
    method = request.method
    
    # 1. Definición de rutas anónimas públicas
    is_public = (
        (method == "GET" and path.startswith("/api/v1/inventory/catalog")) or
        (method == "POST" and path == "/api/v1/clients/register") or
        (method == "POST" and path == "/api/v1/clients/verify-email") or
        (method == "POST" and path == "/api/v1/auth/login")
    )
    
    gateway_secrets = await get_gateway_secrets()

    # Si es ruta pública y no hay token, se permite paso como GUEST
    if is_public and credentials is None:
        return {
            "user_id": "anonymous",
            "username": "guest",
            "roles": ["GUEST"],
            "backend_secret": gateway_secrets["backend_shared_secret"]
        }

    # Si la ruta es protegida y no hay token, se rechaza de inmediato (401)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer token requerido para esta operación")

    introspection_secret = gateway_secrets["auth_introspection_secret"]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/introspect",
                json={"token": credentials.credentials},
                headers={"X-Gateway-Auth-Secret": introspection_secret}
            )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Error de enlace con Authentication Service")

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    identity = response.json()
    if not identity.get("active", False):
        raise HTTPException(status_code=401, detail="Token revocado o expirado")

    return {
        "user_id": str(identity["user_id"]),
        "username": identity["username"],
        "roles": identity.get("roles", ["CLIENT"]),
        "backend_secret": gateway_secrets["backend_shared_secret"]
    }

# Endpoint para login enrutado directamente al auth-service
@app.post("/api/v1/auth/login")
async def gateway_login(request: Request):
    gateway_secrets = await get_gateway_secrets()
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/login",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gateway-Auth-Secret": gateway_secrets["auth_introspection_secret"]
                }
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={"Content-Type": "application/json"}
        )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Auth Service no disponible")

# Proxy dinámico hacia los microservicios internos
@app.api_route(
    "/api/v1/{service}/{subpath:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
)
async def proxy_router(
    service: str,
    subpath: str,
    request: Request,
    auth=Depends(authenticate_request)
):
    if service not in SERVICES_ROUTING:
        raise HTTPException(status_code=404, detail=f"Microservicio '{service}' no encontrado")

    user_roles = auth["roles"]
    
    # Control de roles en Gateway (Módulo 4: RBAC)
    if service == "payments" and not any(r in user_roles for r in ["CASHIER", "ADMIN"]):
        raise HTTPException(status_code=403, detail="Acceso denegado: Se requiere rol Cajero o Admin")
        
    if service == "dispatch" and not any(r in user_roles for r in ["DISPATCH", "ADMIN"]):
        raise HTTPException(status_code=403, detail="Acceso denegado: Exclusivo para despacho y cocina")

    if service == "reports" and not any(r in user_roles for r in ["OWNER", "ADMIN"]):
        raise HTTPException(status_code=403, detail="Acceso denegado: Exclusivo para el Dueño o Administrador")

    target_url = f"{SERVICES_ROUTING[service]}/{subpath}"
    body = await request.body()

    # Headers propagados a la red privada (Zero-Trust)
    forward_headers = {
        "X-Gateway-Secret": auth["backend_secret"],
        "X-Authenticated-User-Id": auth["user_id"],
        "X-Authenticated-User": auth["username"],
        "X-Authenticated-Roles": ",".join(user_roles)
    }

    if "content-type" in request.headers:
        forward_headers["content-type"] = request.headers["content-type"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                content=body,
                headers=forward_headers
            )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail=f"Microservicio '{service}' temporalmente inaccesible")

    response_headers = {}
    if "content-type" in upstream.headers:
        response_headers["content-type"] = upstream.headers["content-type"]

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)