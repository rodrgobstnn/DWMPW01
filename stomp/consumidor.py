import argparse
import json
import time
import xml.etree.ElementTree as ET
import stomp

DESTINO = "/queue/pedidos"

def interpretar(cuerpo: str, headers: dict):
    formato = headers.get("x-formato", "").lower()
    tipo_mime = headers.get("content-type", "").lower()
    if not formato:
        if "application/json" in tipo_mime:
            formato = "json"
        elif "application/xml" in tipo_mime or "text/xml" in tipo_mime:
            formato = "xml"
        else:
            formato = "texto"

    if formato == "texto":
        return formato, cuerpo
    if formato == "fijo":
        if len(cuerpo) != 36:
            raise ValueError(f"Registro de ancho fijo inválido: {len(cuerpo)} se espera 36")
        identificador = cuerpo[0:6]
        cliente = cuerpo[6:26].rstrip()
        monto = cuerpo[26:36]
        if not (identificador.isascii() and identificador.isdigit() and len(monto) == 10 and monto[:7].isdigit() and monto[7] == "." and monto[8:].isdigit()):
            raise ValueError("Campos numéricos de ancho fijo inválidos")
        return formato, {"id": identificador, "cliente": cliente, "monto": monto}
    if formato == "json":
        return formato, json.loads(cuerpo)
    if formato == "xml":
        raiz = ET.fromstring(cuerpo)
        if raiz.tag != "pedido":
            raise ValueError("El nodo raíz de XML debe ser <pedido>")
        return formato, {elemento.tag: elemento.text for elemento in raiz}
    raise ValueError(f"Formato no soportado: {formato}")

def imprimir_comanda_cocina(pedido: dict):
    print("\n" + "="*48)
    print("      FIT EXPRESS - COMANDA DE COCINA (FIFO)")
    print("="*48)
    print(f" Orden N°:      #{pedido.get('id', 'S/N')}")
    print(f" Boleta DTE:    Folio {pedido.get('folio_boleta', 'EMITIDA')}")
    print(f" Cliente:       {pedido.get('cliente', 'Cliente Registrado')}")
    print(f" Monto Total:   ${pedido.get('monto', '0')}")
    print("-"*48)
    print(" ITEMS A PREPARAR:")
    items = pedido.get("items", [])
    if isinstance(items, list):
        for item in items:
            prod = item.get("producto", "Item")
            cant = item.get("cantidad", 1)
            notas = item.get("notas", "Normal")
            print(f"  * [{cant}x] {prod}")
            print(f"       -> Obs: {notas}")
    else:
        print(f"  Detalle: {items}")
    print("-"*48)
    print(" ESTADO: PAGO VALIDADO -> EN PREPARACIÓN")
    print("="*48 + "\n")

class Escuchador(stomp.ConnectionListener):
    def __init__(self, conexion):
        self.conexion = conexion

    def on_error(self, frame):
        print(f"ERROR del broker: {frame.body}")

    def on_disconnected(self):
        print("Conexión STOMP cerrada")

    def on_message(self, frame):
        ack_id = frame.headers["ack"]
        try:
            formato, contenido = interpretar(frame.body, frame.headers)
            print(f"\n[RECIBIDO VIA STOMP] formato={formato}")
            if isinstance(contenido, dict) and "id" in contenido:
                imprimir_comanda_cocina(contenido)
            elif isinstance(contenido, str):
                print(contenido)
            else:
                print(json.dumps(contenido, ensure_ascii=False, indent=2))
            self.conexion.ack(id=ack_id)
        except Exception as exc:
            print(f"[MENSAJE NO VÁLIDO] {exc}")
            self.conexion.nack(id=ack_id, requeue="false")

def main():
    parser = argparse.ArgumentParser(description="Consumidor STOMP Cocina Fit Express")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=61613, type=int)
    parser.add_argument("--usuario", default="demo")
    parser.add_argument("--clave", default="demo123")
    args = parser.parse_args()

    conexion = stomp.Connection12([(args.host, args.port)], vhost="/")
    conexion.set_listener("pedidos", Escuchador(conexion))

    try:
        conexion.connect(args.usuario, args.clave, wait=True)
        conexion.subscribe(
            destination=DESTINO,
            id="lector-pedidos-cocina",
            ack="client-individual",
            headers={"prefetch-count": "1"}
        )
        print(f"[*] Escuchando cola {DESTINO}. Esperando órdenes pagadas... (Ctrl+C para salir)")
        while conexion.is_connected():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo consumidor...")
    finally:
        if conexion.is_connected():
            conexion.disconnect()

if __name__ == "__main__":
    main()