import typing
import httpx
from fastapi import FastAPI
import strawberry
from strawberry.fastapi import GraphQLRouter

INVENTORY_SERVICE_URL = "http://127.0.0.1:9001"

@strawberry.type
class ProductoNutricional:
    id: strawberry.ID
    nombre: str
    categoria: str
    precio: int
    macros: str
    disponible: bool

@strawberry.type
class ItemOrden:
    productoId: int
    cantidad: int
    precioUnitario: int
    subtotal: int
    notas: str

    # Agregación: consulta al microservicio de inventario
    @strawberry.field
    async def productoInfo(self) -> typing.Optional[ProductoNutricional]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{INVENTORY_SERVICE_URL}/catalog")
                for p in resp.json():
                    if p["id"] == self.productoId:
                        return ProductoNutricional(
                            id=strawberry.ID(str(p["id"])),
                            nombre=p["nombre"],
                            categoria=p["categoria"],
                            precio=p["precio"],
                            macros=p["macros"],
                            disponible=p["disponible"]
                        )
        except Exception:
            return None
        return None

@strawberry.type
class OrdenDetalle:
    ordenId: str
    clienteId: str
    clienteNombre: str
    estado: str
    total: int
    folioBoleta: typing.Optional[int]
    fecha: str
    items: typing.List[ItemOrden]

@strawberry.type
class Query:
    @strawberry.field
    def getMisPedidos(self) -> typing.List[OrdenDetalle]:
        return [
            OrdenDetalle(
                ordenId="2001",
                clienteId="CLI-1001",
                clienteNombre="Camilo Morales",
                estado="PAID",
                total=9980,
                folioBoleta=542109,
                fecha="2026-11-10 13:40:00",
                items=[
                    ItemOrden(
                        productoId=101,
                        cantidad=1,
                        precioUnitario=7490,
                        subtotal=7490,
                        notas="Arroz integral, sin pepino"
                    ),
                    ItemOrden(
                        productoId=104,
                        cantidad=1,
                        precioUnitario=2490,
                        subtotal=2490,
                        notas="Normal"
                    )
                ]
            )
        ]

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="Fit Express GraphQL Gateway (Python)")
app.include_router(graphql_app, prefix="/graphql")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)