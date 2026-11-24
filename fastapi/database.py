import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/fitexpress_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ProductoDB(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(120), nullable=False)
    categoria = Column(String(50), nullable=False)
    precio = Column(Integer, nullable=False)
    disponible = Column(Boolean, default=True, nullable=False)
    macros = Column(String(100), default="")
    desc = Column(String(500), default="")
    img = Column(String(500), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "categoria": self.categoria,
            "precio": self.precio,
            "disponible": self.disponible,
            "macros": self.macros,
            "desc": self.desc,
            "img": self.img,
        }


class OrdenDB(Base):
    __tablename__ = "ordenes"

    order_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cliente = Column(String(120), nullable=False)
    correo = Column(String(150), nullable=False)
    user_id = Column(String(50), default="INVITADO")
    estado = Column(String(40), default="PENDING_PAYMENT", nullable=False)
    total = Column(Integer, nullable=False)
    metodo_pago = Column(String(50), nullable=True)
    boleta_folio = Column(String(50), nullable=True)
    creado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("OrdenItemDB", back_populates="orden", cascade="all, delete-orphan")


class OrdenItemDB(Base):
    __tablename__ = "orden_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("ordenes.order_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, nullable=False)
    nombre = Column(String(120), nullable=False)
    precio = Column(Integer, nullable=False)
    cantidad = Column(Integer, nullable=False)

    orden = relationship("OrdenDB", back_populates="items")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db_and_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(ProductoDB).count() == 0:
            productos_iniciales = [
                ProductoDB(
                    nombre="Bowl Pollo Teriyaki & Quinoa",
                    categoria="bowls",
                    precio=6990,
                    disponible=True,
                    macros="45g Proteína | 510 kcal",
                    desc="Pechuga de pollo grillada en salsa teriyaki baja en sodio, quinoa tricolor, palta fresca, edamame y sésamo tostado.",
                    img="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&auto=format&fit=crop&q=80",
                ),
                ProductoDB(
                    nombre="Salmon Keto Fresh",
                    categoria="bowls",
                    precio=8490,
                    disponible=False,
                    macros="42g Proteína | 490 kcal",
                    desc="Filete de salmón austral sellado a la plancha sobre base de espinaca baby, palta hass, pepino y aderezo cítrico de oliva.",
                    img="https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=600&auto=format&fit=crop&q=80",
                ),
                ProductoDB(
                    nombre="Power Beef & Camote Asado",
                    categoria="bowls",
                    precio=7490,
                    disponible=True,
                    macros="48g Proteína | 560 kcal",
                    desc="Posta rosada magra en tiras, cubos de camote asado al romero, brócoli al vapor y hummus artesanal.",
                    img="https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&auto=format&fit=crop&q=80",
                ),
                ProductoDB(
                    nombre="Barritas Proteicas Cacao & Maní",
                    categoria="snacks",
                    precio=2490,
                    disponible=True,
                    macros="20g Proteína | 210 kcal",
                    desc="Pack de 2 barritas horneadas con proteína whey, mantequilla de maní natural, avena integral y cacao 70%.",
                    img="https://images.unsplash.com/photo-1622484212850-eb596d769edc?w=600&auto=format&fit=crop&q=80",
                ),
            ]
            db.add_all(productos_iniciales)
            db.commit()
    finally:
        db.close()