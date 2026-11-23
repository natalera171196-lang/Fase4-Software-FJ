"""Software FJ: gestión de clientes, servicios y reservas."""
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from pathlib import Path
import re
class ErrorGestion(Exception):
    """Error que puede recibir y corregir el usuario."""
class DatosInvalidos(ErrorGestion):
    """Datos faltantes o fuera del formato esperado."""
class OperacionNoPermitida(ErrorGestion):
    """Operación incompatible con el estado actual."""
def texto(valor, campo):
    """Exige texto con contenido."""
    if not isinstance(valor, str) or not valor.strip():
        raise DatosInvalidos(f"{campo} es obligatorio.")
    return valor.strip()
def numero(valor, campo, minimo, maximo):
    """Convierte y valida un número decimal."""
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, ValueError) as error:
        raise DatosInvalidos(f"{campo} debe ser numérico.") from error
    if not resultado.is_finite() or not minimo <= resultado <= maximo:
        raise DatosInvalidos(f"{campo} debe estar entre {minimo} y {maximo}.")
    return resultado
class Entidad(ABC):
    def __init__(self, codigo):
        self._codigo = texto(codigo, "Código").upper()
    @property
    def codigo(self):
        return self._codigo
    @abstractmethod
    def describir(self):
        """Devuelve un resumen de la entidad."""
class Cliente(Entidad):
    def __init__(self, codigo, nombre=None, correo=None, telefono=None):
        super().__init__(codigo)
        self.nombre = texto(nombre, "Nombre")
        self.correo = texto(correo, "Correo")
        self.telefono = texto(telefono, "Teléfono")

        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.correo):
            raise DatosInvalidos("Correo inválido.")
        if not re.fullmatch(r"\+?[0-9]{7,15}", self.telefono):
            raise DatosInvalidos("Teléfono inválido. Escribe entre 7 y 15 dígitos.")
    def describir(self):
        return f"{self.codigo} · {self.nombre}"
class Servicio(Entidad, ABC):
    def __init__(self, codigo, nombre=None, tarifa=None, disponible=True):
        super().__init__(codigo)
        self.nombre = texto(nombre, "Nombre del servicio")
        self.tarifa = numero(tarifa, "Tarifa", Decimal("0.01"), 1000000000)
        if type(disponible) is not bool:
            raise DatosInvalidos("La disponibilidad debe ser True o False.")
        self._disponible = disponible
    @property
    def disponible(self):
        return self._disponible
    @abstractmethod
    def validar(self, duracion):
        """Valida la duración según el tipo de servicio."""
    @abstractmethod
    def costo_base(self, horas):
        """Calcula el costo sin descuento ni impuesto."""
    def calcular_costo(self, duracion, *, descuento=0, impuesto=0):
        horas = self.validar(duracion)
        rebaja = numero(descuento, "Descuento (%)", 0, 100) / 100
        tributo = numero(impuesto, "Impuesto (%)", 0, 100) / 100
        total = self.costo_base(horas) * (1 - rebaja) * (1 + tributo)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
class Sala(Servicio):
    def describir(self):
        return f"Sala: {self.nombre}"
    def validar(self, duracion):
        return numero(duracion, "Horas de sala", 1, 12)
    def costo_base(self, horas):
        return self.tarifa * horas
class Equipo(Servicio):
    def describir(self):
        return f"Equipo: {self.nombre}"
    def validar(self, duracion):
        return numero(duracion, "Horas de alquiler", 1, 24)
    def costo_base(self, horas):
        return self.tarifa * horas + Decimal("5000")
class Asesoria(Servicio):
    def describir(self):
        return f"Asesoría: {self.nombre}"
    def validar(self, duracion):
        horas = numero(duracion, "Horas de asesoría", Decimal("0.5"), 4)
        if horas % Decimal("0.5"):
            raise DatosInvalidos("La asesoría se agenda en bloques de media hora.")
        return horas
    def costo_base(self, horas):
        return self.tarifa * horas * 2
class Reserva(Entidad):
    def __init__(self, codigo, cliente, servicio, duracion):
        super().__init__(codigo)
        if not isinstance(cliente, Cliente) or not isinstance(servicio, Servicio):
            raise DatosInvalidos("La reserva requiere un cliente y un servicio.")
        if not servicio.disponible:
            raise OperacionNoPermitida("El servicio no está disponible.")
        self.cliente = cliente
        self.servicio = servicio
        self.horas = servicio.validar(duracion)
        self._estado = "pendiente"
        self.total = None
    @property
    def estado(self):
        return self._estado
    def procesar(self, *, descuento=0, impuesto=0):
        """Cotiza una reserva pendiente sin cambiar su estado."""
        if self._estado != "pendiente" or not self.servicio.disponible:
            raise OperacionNoPermitida("No se puede procesar esta reserva.")
        return self.servicio.calcular_costo(
            self.horas, descuento=descuento, impuesto=impuesto)
    def confirmar(self, **opciones):
        self.total = self.procesar(**opciones)
        self._estado = "confirmada"
        return self.total
    def cancelar(self):
        if self._estado == "cancelada":
            raise OperacionNoPermitida("La reserva ya está cancelada.")
        self._estado = "cancelada"
    def describir(self):
        return (
            f"{self.codigo} · {self.cliente.codigo} · "
            f"{self.servicio.describir()} · {self.horas} h · {self.estado}")
class Sistema:
    def __init__(self):
        self._clientes = {}
        self._servicios = {}
        self._reservas = {}
    @staticmethod
    def _agregar(registro, entidad):
        if entidad.codigo in registro:
            raise OperacionNoPermitida(f"El código {entidad.codigo} ya existe.")
        registro[entidad.codigo] = entidad
        return entidad
    @staticmethod
    def _buscar(registro, codigo):
        codigo = texto(codigo, "Código").upper()
        if codigo not in registro:
            raise OperacionNoPermitida(f"No se encontró el código {codigo}.")
        return registro[codigo]
    def registrar_cliente(self, codigo, **datos):
        return self._agregar(self._clientes, Cliente(codigo, **datos))
    def crear_servicio(self, tipo, codigo, **datos):
        clases = {"sala": Sala, "equipo": Equipo, "asesoria": Asesoria}
        tipo = texto(tipo, "Tipo de servicio").lower()
        if tipo not in clases:
            raise DatosInvalidos(f"Tipo de servicio desconocido: {tipo}.")
        return self._agregar(self._servicios, clases[tipo](codigo, **datos))
    def reservar(self, codigo, cliente, servicio, duracion):
        titular = self._buscar(self._clientes, cliente)
        seleccionado = self._buscar(self._servicios, servicio)
        return self._agregar(
            self._reservas,
            Reserva(codigo, titular, seleccionado, duracion),)
    def confirmar(self, codigo, **opciones):
        return self._buscar(self._reservas, codigo).confirmar(**opciones)
    def cancelar(self, codigo):
        reserva = self._buscar(self._reservas, codigo)
        reserva.cancelar()
        return reserva
def ejecutar(registro, nombre, operacion):
    """Ejecuta un caso y registra el resultado."""
    try:
        resultado = operacion()
    except ErrorGestion as error:
        registro.warning(
            "%s | %s",
            nombre,
            error,
            exc_info=error.__cause__ is not None,)
        print(f"ERROR CONTROLADO · {nombre} · {error}")
        return False
    except Exception:
        registro.exception("%s | Error inesperado", nombre)
        print(f"ERROR INESPERADO · {nombre}. Consulta el registro.")
        return False
    else:
        detalle = resultado.describir() if isinstance(resultado, Entidad) else resultado
        registro.info("%s | %s", nombre, detalle)
        print(f"OK · {nombre} · {detalle}")
        return True
    finally:
        registro.info("Fin de la operación: %s", nombre)
def simulacion():
    """Ejecuta los 20 casos de prueba en un orden reproducible."""
    ruta = Path(__file__).resolve().with_name("software_fj.log")
    registro = logging.getLogger("software_fj")
    registro.setLevel(logging.INFO)
    registro.propagate = False
    try:
        destino = logging.FileHandler(ruta, encoding="utf-8")
    except OSError as error:
        destino = logging.StreamHandler()
        registro.addHandler(destino)
        destino.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        registro.warning("No se pudo abrir el archivo de registro: %s", error)
    else:
        destino.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        registro.addHandler(destino)
    sistema = Sistema()
    casos = [
        ("Cliente válido", lambda: sistema.registrar_cliente(
            "C01", nombre="Ana Pérez", correo="ana@example.com", telefono="3001234567"
        )),
        ("Cliente con correo inválido", lambda: sistema.registrar_cliente(
            "C02", nombre="Luis", correo="luis@", telefono="3211234567"
        )),
        ("Cliente con datos faltantes", lambda: sistema.registrar_cliente(
            "C03", nombre="Eva"
        )),
        ("Sala válida", lambda: sistema.crear_servicio(
            "sala", "S01", nombre="Sala Norte", tarifa=30000
        )),
        ("Equipo válido", lambda: sistema.crear_servicio(
            "equipo", "S02", nombre="Proyector", tarifa=20000
        )),
        ("Asesoría válida", lambda: sistema.crear_servicio(
            "asesoria", "S03", nombre="Soporte técnico", tarifa=40000
        )),
        ("Tarifa no numérica", lambda: sistema.crear_servicio(
            "sala", "S04", nombre="Sala Sur", tarifa="abc"
        )),
        ("Equipo fuera de servicio", lambda: sistema.crear_servicio(
            "equipo", "S05", nombre="Cámara", tarifa=25000, disponible=False
        )),
        ("Reserva con cliente inexistente", lambda: sistema.reservar(
            "R00", "C99", "S01", 2
        )),
        ("Reserva de servicio no disponible", lambda: sistema.reservar(
            "R00", "C01", "S05", 2
        )),
        ("Reserva con duración inválida", lambda: sistema.reservar(
            "R00", "C01", "S03", 0.75
        )),
        ("Reserva de sala", lambda: sistema.reservar("R01", "C01", "S01", 2)),
        ("Descuento inválido", lambda: sistema.confirmar("R01", descuento=101)),
        ("Confirmación con descuento e impuesto", lambda: sistema.confirmar(
            "R01", descuento=10, impuesto=19
        )),
        ("Confirmación repetida", lambda: sistema.confirmar("R01")),
        ("Reserva de equipo", lambda: sistema.reservar("R02", "C01", "S02", 3)),
        ("Confirmación de equipo", lambda: sistema.confirmar("R02")),
        ("Cancelación de reserva", lambda: sistema.cancelar("R02")),
        ("Reserva de asesoría", lambda: sistema.reservar("R03", "C01", "S03", 1.5)),
        ("Confirmación de asesoría", lambda: sistema.confirmar("R03")),]
    try:
        exitos = sum(ejecutar(registro, nombre, operacion)
                     for nombre, operacion in casos)
        rechazados = len(casos) - exitos
        print(f"\nResumen: {len(casos)} intentos, {exitos} válidos y "
              f"{rechazados} rechazados.")
        print(f"Registro: {ruta}")
    finally:
        registro.removeHandler(destino)
        destino.close()
if __name__ == "__main__":
    simulacion()