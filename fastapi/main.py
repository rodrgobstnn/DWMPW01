import sys
import os
import time
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr

# Asegurar importación del productor STOMP desde la carpeta raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from stomp.productor import publicar_pedido_stomp
except ImportError:
    def publicar_pedido_stomp(pedido, **kwargs):
        print(f"[STOMP SIMULADO] Publicado evento de pedido #{pedido.get('id')}")
        return True

app = FastAPI(title="Fit Express - Microservicios Internos de Dominio")

# Catálogo oficial en memoria (Módulos 1 y 2)
PRODUCTOS = [
    {"id": 101, "nombre": "Titanium Beef Bowl", "categoria": "bowls", "precio": 7490, "macros": "42g Proteína", "disponible": True},
    {"id": 102, "nombre": "Chicken Power Quinoa", "categoria": "bowls", "precio": 6990, "macros": "38g Proteína", "disponible": True},
    {"id": 103, "nombre": "Salmon Keto Fresh", "categoria": "bowls", "precio": 8290, "macros": "36g Proteína", "disponible": False},
    {"id": 104, "nombre": "Protein Oat Bar (Cacao)", "categoria": "snacks", "precio": 2490, "macros": "18g Proteína", "disponible": True},
    {"id": 105, "nombre": "Peanut Butter Fit Cookies", "categoria": "snacks", "precio": 2290, "macros": "14g Proteína", "disponible": True}
]

ORDENES = {
    2001: {
        "orden_id": 2001,
        "cliente_id": "CLI-1001",
        "cliente_nombre": "Camilo Morales",
        "cliente_email": "camilo@fitexpress.cl",
        "estado": "PAID",
        "total": 9980,
        "folio_boleta": 542109,
        "items": [
            {"producto": "Titanium Beef Bowl", "cantidad": 1, "precio_unitario": 7490, "subtotal": 7490, "notas": "Arroz integral"},
            {"producto": "Protein Oat Bar (Cacao)", "cantidad": 1, "precio_unitario": 2490, "subtotal": 2490, "notas": "Normal"}
        ],
        "fecha": "2026-11-10 13:40:00"
    }
}

FOLIO_ACTUAL = 542109

# Verificación de origen Zero-Trust (Solo peticiones del API Gateway)
def verificar_gateway(x_gateway_secret: str = Header(default="")):
    if x_gateway_secret != "fit_shared_secret_2026":
        raise HTTPException(
            status_code=403, 
            detail="Acceso denegado: El microservicio solo acepta llamadas a través del API Gateway"
        )

# ==========================================
# 1. SUBSISTEMA INVENTORY (RF 1, RF 7)
# ==========================================
@app.get("/catalog")
def get_catalog(categoria: Optional[str] = None, onlyAvailable: bool = False):
    items = PRODUCTOS
    if onlyAvailable:
        items = [p for p in items if p["disponible"]]
    if categoria and categoria != "todos":
        items = [p for p in items if p["categoria"] == categoria]
    return items

@app.patch("/products/{prod_id}/availability")
def set_availability(prod_id: int, available: bool, x_gateway_secret: str = Header(default="")):
    verificar_gateway(x_gateway_secret)
    for p in PRODUCTOS:
        if p["id"] == prod_id:
            p["disponible"] = available
            return {"id": prod_id, "nombre": p["nombre"], "disponible": available}
    raise HTTPException(status_code=404, detail="Producto no encontrado")

# ==========================================
# 2. SUBSISTEMA CLIENTS (RF 5, RF 6, RF 11)
# ==========================================
class VerifyEmailRequest(BaseModel):
    email: EmailStr

@app.post("/verify-email")
def verify_email_api(req: VerifyEmailRequest):
    # Simulación de consulta a API de mensajería externa (RNF 6)
    if "error" in req.email:
        raise HTTPException(status_code=422, detail="La casilla de correo no responde en el servidor de destino")
    return {"email": req.email, "valid": True, "deliverable": True}

# ==========================================
# 3. SUBSISTEMA ORDERS (RF 1, RF 2, RF 3, RF 4)
# ==========================================
class ItemPedidoInput(BaseModel):
    product_id: int
    quantity: int
    notes: Optional[str] = "Normal"

class CrearOrdenInput(BaseModel):
    items: List[ItemPedidoInput]

@app.post("/orders")
def create_order(
    req: CrearOrdenInput,
    x_authenticated_user_id: str = Header(default="anonymous"),
    x_gateway_secret: str = Header(default="")
):
    verificar_gateway(x_gateway_secret)
    if not req.items:
        raise HTTPException(status_code=400, detail="El pedido no puede estar vacío")

    # El servidor recalcula el total según inventario oficial (Regla de oro de la pauta)
    total = 0
    items_calculados = []
    for item in req.items:
        prod = next((p for p in PRODUCTOS if p["id"] == item.product_id), None)
        if not prod:
            raise HTTPException(status_code=400, detail=f"Producto {item.product_id} no existe")
        if not prod["disponible"]:
            raise HTTPException(status_code=400, detail=f"El producto '{prod['nombre']}' se encuentra agotado")

        subtotal = prod["precio"] * item.quantity
        total += subtotal
        items_calculados.append({
            "producto": prod["nombre"],
            "cantidad": item.quantity,
            "precio_unitario": prod["precio"],
            "subtotal": subtotal,
            "notas": item.notes
        })

    order_id = len(ORDENES) + 2001
    nueva_orden = {
        "orden_id": order_id,
        "cliente_id": x_authenticated_user_id,
        "cliente_nombre": "Camilo Morales",
        "cliente_email": "camilo@fitexpress.cl",
        "estado": "PENDING_PAYMENT",
        "total": total,
        "items": items_calculados,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    ORDENES[order_id] = nueva_orden
    return nueva_orden

@app.get("/orders/my-orders")
def get_my_orders(
    x_authenticated_user_id: str = Header(default=""),
    x_gateway_secret: str = Header(default="")
):
    verificar_gateway(x_gateway_secret)
    # Control IDOR: solo devuelve las órdenes del usuario en sesión
    mis_ordenes = [o for o in ORDENES.values() if o["cliente_id"] == x_authenticated_user_id]
    return mis_ordenes

@app.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: int,
    reason: str = Query(..., min_length=5),
    x_authenticated_user_id: str = Header(default=""),
    x_gateway_secret: str = Header(default="")
):
    verificar_gateway(x_gateway_secret)
    orden = ORDENES.get(order_id)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    orden["estado"] = "CANCEL_REQUESTED"
    orden["motivo_anulacion"] = reason
    return {"message": "Solicitud de anulación registrada con éxito", "orden_id": order_id, "motivo": reason}

# ==========================================
# 4. SUBSISTEMA PAYMENTS / CAJA (RF 2, RF 4, RF 8)
# ==========================================
class CheckoutInput(BaseModel):
    order_id: int
    cash_register_id: str = "CAJA-01"

@app.get("/pending-orders")
def get_pending_orders(x_gateway_secret: str = Header(default="")):
    verificar_gateway(x_gateway_secret)
    pendientes = [o for o in ORDENES.values() if o["estado"] == "PENDING_PAYMENT"]
    return pendientes

@app.post("/checkout")
def process_checkout(req: CheckoutInput, x_gateway_secret: str = Header(default="")):
    verificar_gateway(x_gateway_secret)
    global FOLIO_ACTUAL
    orden = ORDENES.get(req.order_id)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden["estado"] == "PAID":
        raise HTTPException(status_code=409, detail="La orden ya se encuentra pagada")

    # 1. Transición oficial de estado
    FOLIO_ACTUAL += 1
    orden["estado"] = "PAID"
    orden["folio_boleta"] = FOLIO_ACTUAL
    orden["caja"] = req.cash_register_id

    # 2. Emisión de evento asíncrono a cocina/despacho mediante STOMP (Módulo 3 y 9)
    evento_cocina = {
        "id": str(orden["orden_id"]),
        "cliente": orden.get("cliente_nombre", "Camilo Morales")[:20],
        "monto": f"{orden['total']}.00",
        "folio_boleta": FOLIO_ACTUAL,
        "items": orden["items"]
    }
    publicar_pedido_stomp(pedido=evento_cocina, formato="json")

    return {
        "status": "CONFIRMED",
        "orden_id": orden["orden_id"],
        "folio_boleta": FOLIO_ACTUAL,
        "total_pagado": orden["total"],
        "mensaje": f"Pago registrado. Boleta enviada a {orden['cliente_email']} y orden transferida a cocina."
    }

# ==========================================
# 5. SUBSISTEMA DISPATCH & REPORTS (RF 9, RF 13)
# ==========================================
@app.get("/dispatch-queue")
def get_dispatch_queue(x_gateway_secret: str = Header(default="")):
    verificar_gateway(x_gateway_secret)
    cola = [o for o in ORDENES.values() if o["estado"] == "PAID"]
    return cola

@app.get("/sales-summary")
def get_sales_summary(x_gateway_secret: str = Header(default="")):
    verificar_gateway(x_gateway_secret)
    total_recaudado = sum(o["total"] for o in ORDENES.values() if o["estado"] == "PAID")
    pagadas = len([o for o in ORDENES.values() if o["estado"] == "PAID"])
    anuladas = len([o for o in ORDENES.values() if o["estado"] == "CANCEL_REQUESTED"])
    return {
        "total_recaudado": total_recaudado,
        "ordenes_pagadas": pagadas,
        "ordenes_anuladas": anuladas,
        "transacciones": list(ORDENES.values())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9001)