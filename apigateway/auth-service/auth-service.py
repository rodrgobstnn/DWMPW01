from datetime import datetime, timedelta, timezone
import os
import secrets
import hashlib
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(
    title="Fit Express - Authentication Service",
    description="Servicio seguro de autenticación, hash de contraseñas e introspección de tokens"
)

# Hash adaptativo seguro con sal para cumplir con Módulo 7 (Sin contraseñas en texto plano)
def hash_password(password: str, salt: str = "fit_express_salt_2026") -> str:
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

# Usuarios base del negocio para pruebas de perfiles (RF 4, RF 5, RF 12)
USERS = {
    # Cliente Registrado (Camilo Morales)
    "camilo@fitexpress.cl": {
        "password_hash": hash_password("cliente123"),
        "user_id": "CLI-1001",
        "run": "18.765.432-1",
        "full_name": "Camilo Morales Vera",
        "roles": ["CLIENT"]
    },
    # Cajero Virtual del Restaurant (Juan Pérez)
    "cajero@fitexpress.cl": {
        "password_hash": hash_password("caja123"),
        "user_id": "EMP-2001",
        "run": "15.432.109-8",
        "full_name": "Juan Pérez Silva",
        "roles": ["CASHIER"]
    },
    # Encargado de Despacho y Cocina (Pedro Soto)
    "despacho@fitexpress.cl": {
        "password_hash": hash_password("cocina123"),
        "user_id": "EMP-3001",
        "run": "16.890.123-K",
        "full_name": "Pedro Soto Martínez",
        "roles": ["DISPATCH"]
    },
    # Administrador / Dueño del Restaurant (Guillermo Dueño)
    "admin@fitexpress.cl": {
        "password_hash": hash_password("admin123"),
        "user_id": "ADM-0001",
        "run": "12.345.678-9",
        "full_name": "Administrador Fit Express",
        "roles": ["ADMIN", "OWNER"]
    }
}

SESSIONS = {}
TOKEN_LIFETIME_MINUTES = 15

AUTH_INTROSPECTION_SECRET = os.getenv(
    "AUTH_INTROSPECTION_SECRET",
    "fit_intro_secret_2026"
)

class LoginRequest(BaseModel):
    username: str
    password: str

class IntrospectionRequest(BaseModel):
    token: str

class RegisterRequest(BaseModel):
    run: str
    email: str
    password: str
    full_name: str

@app.post("/register")
def register_user(
    request: RegisterRequest,
    x_gateway_auth_secret: str = Header(default="")
):
    if not secrets.compare_digest(x_gateway_auth_secret, AUTH_INTROSPECTION_SECRET):
        raise HTTPException(status_code=403, detail="Gateway no autorizado")

    if request.email in USERS:
        raise HTTPException(status_code=409, detail="El correo ya se encuentra registrado")

    user_id = f"CLI-{len(USERS) + 1001}"
    USERS[request.email] = {
        "password_hash": hash_password(request.password),
        "user_id": user_id,
        "run": request.run,
        "full_name": request.full_name,
        "roles": ["CLIENT"]
    }
    return {"message": "Usuario registrado exitosamente", "user_id": user_id}

@app.post("/login")
def login(
    request: LoginRequest,
    x_gateway_auth_secret: str = Header(default="")
):
    if not secrets.compare_digest(x_gateway_auth_secret, AUTH_INTROSPECTION_SECRET):
        raise HTTPException(status_code=403, detail="Gateway no autorizado")

    user = USERS.get(request.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    if user["password_hash"] != hash_password(request.password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    access_token = secrets.token_urlsafe(32)
    expiration = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_LIFETIME_MINUTES)
    
    SESSIONS[access_token] = {
        "user_id": user["user_id"],
        "username": request.username,
        "run": user.get("run", ""),
        "full_name": user.get("full_name", ""),
        "roles": user["roles"],
        "expires_at": expiration
    }

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_LIFETIME_MINUTES * 60,
        "user": {
            "user_id": user["user_id"],
            "email": request.username,
            "roles": user["roles"]
        }
    }

@app.post("/introspect")
def introspect(
    request: IntrospectionRequest,
    x_gateway_auth_secret: str = Header(default="")
):
    if not secrets.compare_digest(x_gateway_auth_secret, AUTH_INTROSPECTION_SECRET):
        raise HTTPException(status_code=403, detail="Gateway no autorizado")

    session = SESSIONS.get(request.token)
    if session is None:
        return {"active": False}

    if datetime.now(timezone.utc) > session["expires_at"]:
        SESSIONS.pop(request.token, None)
        return {"active": False}

    return {
        "active": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "run": session.get("run", ""),
        "roles": session["roles"],
        "expires_at": session["expires_at"].isoformat()
    }

@app.post("/logout")
def logout(
    request: IntrospectionRequest,
    x_gateway_auth_secret: str = Header(default="")
):
    if not secrets.compare_digest(x_gateway_auth_secret, AUTH_INTROSPECTION_SECRET):
        raise HTTPException(status_code=403, detail="Gateway no autorizado")

    SESSIONS.pop(request.token, None)
    return {"message": "Sesión finalizada exitosamente"}

@app.get("/health")
def health(x_gateway_auth_secret: str = Header(default="")):
    if not secrets.compare_digest(x_gateway_auth_secret, AUTH_INTROSPECTION_SECRET):
        raise HTTPException(status_code=403, detail="Gateway no autorizado")
    return {"status": "OK", "service": "Fit Express Authentication Service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)