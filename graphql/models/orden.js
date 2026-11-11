const mongoose = require('mongoose');

const ordenSchema = new mongoose.Schema({
  ordenId: { type: Number, required: true, unique: true },
  clienteId: { type: String, required: true },
  clienteNombre: { type: String, required: true },
  clienteEmail: { type: String, required: true },
  estado: { 
    type: String, 
    enum: ['PENDING_PAYMENT', 'PAID', 'IN_KITCHEN', 'DISPATCHED', 'CANCEL_REQUESTED', 'CANCELLED'],
    default: 'PENDING_PAYMENT' 
  },
  total: { type: Number, required: true },
  folioBoleta: { type: Number, default: null },
  motivoAnulacion: { type: String, default: null },
  items: [
    {
      productoId: { type: Number, required: true },
      cantidad: { type: Number, required: true },
      precioUnitario: { type: Number, required: true },
      subtotal: { type: Number, required: true },
      notas: { type: String, default: 'Normal' }
    }
  ],
  fechaCreacion: { type: Date, default: Date.now }
});

module.exports = mongoose.model('Orden', ordenSchema);