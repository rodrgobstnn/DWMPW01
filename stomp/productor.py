import argparse
import json
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
import stomp

DESTINO = "/queue/pedidos"

def construir_mensaje(formato: str, pedido: dict, texto: str) -> tuple[str, str]:
    if formato == "texto":
        return texto, "text/plain; charset=utf-8"
    if formato == "fijo":
        # Contrato Fixed 36 chars: ID[6], CLIENTE[20], MONTO[10]
        identificador = str(pedido["id"])
        cliente = str(pedido["cliente"])
        monto = Decimal(str(pedido["monto"]))
        monto_campo = f"{monto:010.2f}"
        if not (identificador.isascii() and identificador.isdigit() and len(identificador) <= 6):
            raise ValueError("En formato fijo, --id debe tener hasta 6 digitos ASCII")
        if len(cliente) > 20 or any(ord(c) > 127 for c in cliente):
            raise ValueError("En formato fijo, --cliente admite hasta 20 caracteres ASCII")
        if monto < 0 or len(monto_campo) != 10:
            raise ValueError("En formato fijo, --monto debe estar entre 0 y 99999999.99")
        return f"{identificador.zfill(6)}{cliente:<20}{monto_campo}", "text/plain; charset=utf-8"
    if formato == "json":
        return json.dumps(pedido, ensure_ascii=False), "application/json; charset=utf-8"
    if formato == "xml":
        raiz = ET.Element("pedido")
        for clave, valor in pedido.items():
            sub = ET.SubElement(raiz, clave)
            if isinstance(valor, (dict, list)):
                sub.text = json.dumps(valor, ensure_ascii=False)
            else:
                sub.text = str(valor)
        return ET.tostring(raiz, encoding="unicode"), "application/xml; charset=utf-8"
    raise ValueError(f"Formato desconocido: {formato}")

def publicar_pedido_stomp(
    pedido: dict,
    formato: str = "json",
    host: str = "127.0.0.1",
    port: int = 61613,
    usuario: str = "demo",
    clave: str = "demo123"
) -> bool:
    """Función de publicación directa llamada desde FastAPI al cobrar."""
    cuerpo, mime = construir_mensaje(formato, pedido, texto="")
    conexion = stomp.Connection12([(host, port)], vhost="/")
    try:
        conexion.connect(usuario, clave, wait=True)
        conexion.send(
            destination=DESTINO,
            body=cuerpo,
            headers={
                "content-type": mime,
                "x-formato": formato,
                "persistent": "true",
            },
        )
        print(f"[STOMP] Pedido #{pedido.get('id')} enviado exitosamente a {DESTINO}")
        return True
    except Exception as exc:
        print(f"[STOMP AVISO] No se pudo conectar al broker STOMP (¿Activo en 61613?): {exc}")
        return False
    finally:
        if conexion.is_connected():
            conexion.disconnect()

def main():
    parser = argparse.ArgumentParser(description="Productor STOMP - Fit Express")
    parser.add_argument("--formato", choices=["texto", "fijo", "xml", "json"], required=True)
    parser.add_argument("--mensaje", default="Nueva orden Fit Express en preparación")
    parser.add_argument("--id", default="2002")
    parser.add_argument("--cliente", default="Camilo Morales")
    parser.add_argument("--monto", default="13980.00")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=61613, type=int)
    parser.add_argument("--usuario", default="demo")
    parser.add_argument("--clave", default="demo123")
    args = parser.parse_args()

    try:
        monto = Decimal(args.monto)
        if not monto.is_finite():
            raise ValueError("El monto debe ser finito")
    except InvalidOperation:
        parser.error(f"Monto no válido: {args.monto}")

    pedido = {
        "id": args.id,
        "cliente": args.cliente,
        "monto": str(monto),
        "items": [
            {"producto": "Chicken Power Quinoa", "cantidad": 2, "notas": "Sin pepino"}
        ]
    }

    try:
        cuerpo, mime = construir_mensaje(args.formato, pedido, args.mensaje)
    except ValueError as exc:
        parser.error(str(exc))

    conexion = stomp.Connection12([(args.host, args.port)], vhost="/")
    try:
        conexion.connect(args.usuario, args.clave, wait=True)
        conexion.send(
            destination=DESTINO,
            body=cuerpo,
            headers={
                "content-type": mime,
                "x-formato": args.formato,
                "persistent": "true",
            },
        )
        print(f"Mensaje enviado a {DESTINO} (formato={args.formato}):\n{cuerpo}")
    finally:
        if conexion.is_connected():
            conexion.disconnect()

if __name__ == "__main__":
    main()