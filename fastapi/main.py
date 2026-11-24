import os
import secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uvicorn

from database import (
    get_db,
    init_db_and_seed,
    ProductoDB,
    OrdenDB,
    OrdenItemDB,
)

app = FastAPI(title="Fit Express Core Backend (PostgreSQL + Zero-Trust)", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "fit_shared_secret_2026")


def verificar_gateway(x_gateway_secret: str = Header(default="")):
    if not secrets.compare_digest(x_gateway_secret, GATEWAY_SECRET):
        print("\n[BACKEND-CORE] BLOQUEADO (403): Llamada directa sin secreto válido X-Gateway-Secret.")
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: El microservicio solo acepta llamadas a través del API Gateway"
        )
    print("\n[BACKEND-CORE] Secreto Zero-Trust X-Gateway-Secret VERIFICADO OK. Ejecutando consulta en PostgreSQL...")


@app.on_event("startup")
def on_startup():
    init_db_and_seed()


class NuevoProductoInput(BaseModel):
    nombre: str
    categoria: str
    precio: int
    macros: str = ""
    desc: str = ""
    img: str = ""


class ItemOrdenInput(BaseModel):
    id: int
    nombre: str
    precio: int
    cantidad: int


class NuevaOrdenInput(BaseModel):
    cliente: str
    correo: str
    items: List[ItemOrdenInput]
    total: int


class PagoInput(BaseModel):
    order_id: int
    metodo_pago: str


# ================= CATÁLOGO E INVENTARIO =================

@app.get("/catalog")
def get_catalog(
    onlyAvailable: bool = True,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    query = db.query(ProductoDB)
    if onlyAvailable:
        query = query.filter(ProductoDB.disponible == True)
    productos = query.order_by(ProductoDB.id.asc()).all()
    return [p.to_dict() for p in productos]


@app.get("/products")
def list_products(
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    productos = db.query(ProductoDB).order_by(ProductoDB.id.asc()).all()
    return [p.to_dict() for p in productos]


@app.post("/products", status_code=201)
def create_product(
    data: NuevoProductoInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    nuevo = ProductoDB(
        nombre=data.nombre,
        categoria=data.categoria,
        precio=data.precio,
        disponible=True,
        macros=data.macros,
        descripcion=data.desc,
        img=data.img,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    print(f"[BACKEND-CORE] Producto ID #{nuevo.id} ('{nuevo.nombre}') persistido en PostgreSQL.")
    return nuevo.to_dict()


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    data: NuevoProductoInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    prod = db.query(ProductoDB).filter(ProductoDB.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    prod.nombre = data.nombre
    prod.categoria = data.categoria
    prod.precio = data.precio
    prod.macros = data.macros
    prod.descripcion = data.desc
    if data.img is not None:
        prod.img = data.img

    db.commit()
    db.refresh(prod)
    print(f"[BACKEND-CORE] Producto ID #{prod.id} actualizado en PostgreSQL.")
    return prod.to_dict()


@app.patch("/products/{product_id}/availability")
def toggle_availability(
    product_id: int,
    available: bool,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    prod = db.query(ProductoDB).filter(ProductoDB.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    prod.disponible = available
    db.commit()
    db.refresh(prod)
    print(f"[BACKEND-CORE] Disponibilidad de producto ID #{prod.id} cambiada a {available} en PostgreSQL.")
    return prod.to_dict()


# ================= ÓRDENES Y PAGOS =================

@app.post("/orders", status_code=201)
def crear_orden(
    data: NuevaOrdenInput,
    x_authenticated_user_id: str = Header(default="INVITADO"),
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="El carrito no puede estar vacío")

    nueva_orden = OrdenDB(
        cliente=data.cliente,
        correo=data.correo,
        user_id=x_authenticated_user_id or "INVITADO",
        estado="PENDING_PAYMENT",
        total=data.total,
    )
    db.add(nueva_orden)
    db.flush()

    for it in data.items:
        db.add(
            OrdenItemDB(
                order_id=nueva_orden.order_id,
                product_id=it.id,
                nombre=it.nombre,
                precio=it.precio,
                cantidad=it.cantidad,
            )
        )

    db.commit()
    db.refresh(nueva_orden)
    return {
        "message": "Orden creada en estado PENDING_PAYMENT",
        "order_id": nueva_orden.order_id,
        "estado": nueva_orden.estado,
        "total": nueva_orden.total,
    }


@app.get("/pending")
def listar_ordenes_pendientes(
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    ordenes = (
        db.query(OrdenDB)
        .filter(OrdenDB.estado == "PENDING_PAYMENT")
        .order_by(OrdenDB.order_id.asc())
        .all()
    )
    resultado = []
    for o in ordenes:
        resultado.append({
            "order_id": o.order_id,
            "cliente": o.cliente,
            "correo": o.correo,
            "estado": o.estado,
            "total": o.total,
            "items": [
                {
                    "id": i.product_id,
                    "nombre": i.nombre,
                    "precio": i.precio,
                    "cantidad": i.cantidad,
                }
                for i in o.items
            ],
        })
    return resultado


@app.post("/process")
def procesar_pago(
    data: PagoInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_gateway),
):
    orden = db.query(OrdenDB).filter(OrdenDB.order_id == data.order_id).first()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail=f"La orden ya se encuentra en estado {orden.estado}")

    folio = f"BOL-{orden.order_id:05d}"
    orden.estado = "PAID_IN_KITCHEN"
    orden.metodo_pago = data.metodo_pago
    orden.boleta_folio = folio
    db.commit()
    db.refresh(orden)

    return {
        "message": "Pago aprobado y orden enviada a cocina",
        "order_id": orden.order_id,
        "estado": orden.estado,
        "boleta_folio": folio,
        "metodo_pago": orden.metodo_pago,
        "total": orden.total,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9001)