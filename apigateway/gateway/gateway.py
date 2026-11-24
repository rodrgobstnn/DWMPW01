import os
import uuid
import httpx
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn

app = FastAPI(title="Fit Express API Gateway (Zero-Trust)", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "fit_shared_secret_2026")
AUTH_INTROSPECTION_SECRET = os.getenv("AUTH_INTROSPECTION_SECRET", "fit_intro_secret_2026")
AUTH_SERVICE_URL = "http://127.0.0.1:8100"

SERVICES = {
    "auth": "http://127.0.0.1:8100",
    "inventory": "http://127.0.0.1:9001",
    "orders": "http://127.0.0.1:9001",
    "payments": "http://127.0.0.1:9001",
    "graphql": "http://127.0.0.1:8090",
}

PUBLIC_ENDPOINTS = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/register"),
    ("GET", "/api/v1/inventory/catalog"),
    ("GET", "/api/v1/inventory/products"),
    ("POST", "/api/v1/orders/verify-email"),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "Frontend_FitExpress"))
UPLOAD_DIR = os.path.join(FRONTEND_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def validar_token_y_rol(request: Request, require_admin: bool = False) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        print("[API-GATEWAY] BLOQUEADO: Petición sin token Bearer.")
        raise HTTPException(status_code=401, detail="Token faltante o formato inválido")

    token = auth_header.removeprefix("Bearer ").strip()
    print(f"[API-GATEWAY] -> Solicitando validación de token y roles al Auth Service (:8100/introspect)...")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{AUTH_SERVICE_URL}/introspect",
                json={"token": token},
                headers={"X-Gateway-Auth-Secret": AUTH_INTROSPECTION_SECRET},
                timeout=5.0,
            )
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Servicio de autenticación no disponible")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Error al verificar la sesión")

    session_data = resp.json()
    if not session_data.get("active"):
        print("[API-GATEWAY] <- Auth Service rechazó el token (expirado o inválido).")
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")

    roles = [str(r).upper() for r in session_data.get("roles", [])]
    print(f"[API-GATEWAY] <- Auth Service aprobó sesión: usuario={session_data.get('username')} | roles={roles}")

    if require_admin and not any(r in {"ADMIN", "OWNER"} for r in roles):
        print(f"[API-GATEWAY] BLOQUEADO (403): Usuario {session_data.get('username')} no tiene rol ADMIN/OWNER.")
        raise HTTPException(status_code=403, detail="Acceso denegado: Se requiere rol de administrador")

    return session_data


@app.post("/api/v1/upload-image")
async def upload_product_image(request: Request, file: UploadFile = File(...)):
    print("\n[API-GATEWAY] Petición recibida desde Frontend: POST /api/v1/upload-image")
    await validar_token_y_rol(request, require_admin=True)

    allowed_ext = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Formato de imagen no permitido.")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    print(f"[API-GATEWAY] Imagen guardada localmente en /app/uploads/{filename}")
    return {"url": f"/app/uploads/{filename}"}


@app.api_route("/api/v1/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway_proxy(service: str, path: str, request: Request):
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Microservicio '{service}' no registrado")

    full_path = f"/api/v1/{service}/{path}"
    method = request.method.upper()
    is_public = (method, full_path) in PUBLIC_ENDPOINTS

    print(f"\n[API-GATEWAY] Petición recibida desde Frontend: {method} {full_path}")

    user_headers = {}
    if not is_public:
        require_admin = (
            method in {"POST", "PUT", "PATCH", "DELETE"}
            and full_path.startswith("/api/v1/inventory/products")
        )
        session_data = await validar_token_y_rol(request, require_admin=require_admin)
        user_headers["X-Authenticated-User-Id"] = str(session_data.get("user_id", ""))
        user_headers["X-User-Email"] = str(session_data.get("username", ""))
        user_headers["X-User-Roles"] = ",".join(session_data.get("roles", []))
    else:
        print(f"[API-GATEWAY] Ruta pública ({method} {full_path}), omitiendo introspección JWT.")

    target_base = SERVICES[service]
    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    print(f"[API-GATEWAY] -> Enrutando petición hacia Backend [{service.upper()}] en {target_url} con secreto Zero-Trust")

    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }
    forward_headers["X-Gateway-Secret"] = GATEWAY_SECRET
    forward_headers["X-Gateway-Auth-Secret"] = AUTH_INTROSPECTION_SECRET
    forward_headers.update(user_headers)

    body = await request.body()

    async with httpx.AsyncClient() as client:
        try:
            proxy_resp = await client.request(
                method=method,
                url=target_url,
                headers=forward_headers,
                content=body,
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error con microservicio '{service}': {exc}")

    print(f"[API-GATEWAY] <- Respuesta de [{service.upper()}]: HTTP {proxy_resp.status_code}")

    excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    resp_headers = {
        k: v for k, v in proxy_resp.headers.items() if k.lower() not in excluded_headers
    }

    return Response(
        content=proxy_resp.content,
        status_code=proxy_resp.status_code,
        headers=resp_headers,
    )


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/app/index.html")


if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)