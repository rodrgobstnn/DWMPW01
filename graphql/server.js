const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const axios = require('axios');
const { ApolloServer, gql } = require('apollo-server-express');

// Conexión a MongoDB bdunab2 (misma URI del profesor)
const MONGO_URI = process.env.MONGO_URI || 'mongodb://localhost:27017/bdunab2';
mongoose.connect(MONGO_URI)
  .then(() => console.log('[GraphQL] Conectado exitosamente a MongoDB bdunab2'))
  .catch(err => console.log('[GraphQL Aviso] MongoDB local no disponible (operando en modo memoria):', err.message));

// Microservicio FastAPI de inventario
const INVENTORY_SERVICE_URL = process.env.INVENTORY_SERVICE_URL || 'http://127.0.0.1:9001';

const typeDefs = gql`
  type ProductoNutricional {
    id: ID!
    nombre: String!
    categoria: String!
    precio: Int!
    macros: String
    disponible: Boolean!
  }

  type ItemOrden {
    productoId: ID!
    cantidad: Int!
    precioUnitario: Int!
    subtotal: Int!
    notas: String
    # Campo enriquecido desde FastAPI Inventory (Agregación Módulo 8)
    productoInfo: ProductoNutricional
  }

  type OrdenDetalle {
    ordenId: ID!
    clienteId: String!
    clienteNombre: String!
    clienteEmail: String!
    estado: String!
    total: Int!
    folioBoleta: Int
    motivoAnulacion: String
    items: [ItemOrden!]!
    fecha: String
  }

  type AlertResponse {
    success: Boolean!
    message: String!
  }

  type Query {
    getMisPedidos: [OrdenDetalle!]!
    getCatalogo: [ProductoNutricional!]!
  }

  type Mutation {
    solicitarAnulacion(ordenId: ID!, motivo: String!): AlertResponse
  }
`;

const resolvers = {
  Query: {
    async getMisPedidos(parent, args, context) {
      // Datos de pedidos listos para resolver la vista 'mis-pedidos.html'
      return [
        {
          ordenId: "2001",
          clienteId: context.userId || "CLI-1001",
          clienteNombre: "Camilo Morales",
          clienteEmail: "camilo@fitexpress.cl",
          estado: "PAID",
          total: 9980,
          folioBoleta: 542109,
          motivoAnulacion: null,
          fecha: "2026-11-10 13:40:00",
          items: [
            {
              productoId: 101,
              cantidad: 1,
              precioUnitario: 7490,
              subtotal: 7490,
              notas: "Arroz integral, sin pepino"
            },
            {
              productoId: 104,
              cantidad: 1,
              precioUnitario: 2490,
              subtotal: 2490,
              notas: "Normal"
            }
          ]
        }
      ];
    },

    async getCatalogo() {
      try {
        const resp = await axios.get(`${INVENTORY_SERVICE_URL}/catalog`, {
          params: { onlyAvailable: false }
        });
        return resp.data;
      } catch (e) {
        return [];
      }
    }
  },

  // Resolver anidado de agregación: consulta a FastAPI para enriquecer los macros
  ItemOrden: {
    async productoInfo(parent) {
      try {
        const resp = await axios.get(`${INVENTORY_SERVICE_URL}/catalog`, {
          params: { onlyAvailable: false }
        });
        const producto = resp.data.find(p => String(p.id) === String(parent.productoId));
        return producto || null;
      } catch (e) {
        return null;
      }
    }
  },

  Mutation: {
    async solicitarAnulacion(parent, { ordenId, motivo }) {
      if (!motivo || motivo.trim().length < 5) {
        return {
          success: false,
          message: "El motivo debe tener al menos 5 caracteres."
        };
      }
      return {
        success: true,
        message: `Solicitud de anulación registrada para la orden #${ordenId}.`
      };
    }
  }
};

const app = express();
app.use(cors());

let apolloServer = null;

async function startServer() {
  apolloServer = new ApolloServer({
    typeDefs,
    resolvers,
    context: ({ req }) => {
      const userId = req.headers['x-authenticated-user-id'] || 'CLI-1001';
      const userRoles = req.headers['x-authenticated-roles'] || 'CLIENT';
      return { userId, userRoles };
    }
  });

  await apolloServer.start();
  apolloServer.applyMiddleware({ app, path: '/graphql', cors: false });
}

startServer();

const PORT = process.env.PORT || 8090;
app.listen(PORT, function () {
  console.log(`[GraphQL Gateway] Activo en http://localhost:${PORT}/graphql`);
});