#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Microservicio Central de Consecutivos y Padrón Metrológico - CENAM
=================================================================
Provee un servicio en la nube o red para despachar folios consecutivos
atómicos a múltiples locaciones remotas y centralizar la trazabilidad
y auditoría de certificados e informes bajo ISO/IEC 17025.
"""

import os
import sys
import io
import csv
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Soporte de importación dual para despliegue independiente (Render, Cloud Run, Docker)
# o como módulo dentro de la solución completa
try:
    import db_consecutivos as db
except ImportError:
    try:
        import servidor_consecutivos.db_consecutivos as db
    except ImportError:
        from . import db_consecutivos as db

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Inicializar Base de Datos en el arranque
db.init_db()

app = FastAPI(
    title="CENAM - Servidor Central de Consecutivos y Padrón",
    description="Servicio centralizado atómico para control de folios consecutivos y padrón multilocación",
    version="1.0.0"
)

# -------------------------------------------------------------
# MODELOS DE DATOS PYDANTIC
# -------------------------------------------------------------
class SolicitarConsecutivoReq(BaseModel):
    area_codigo: str = Field(default="740", description="Código de área metrológica (ej. 740)")
    ano: int = Field(default=2026, description="Año de emisión")
    tipo_documento: str = Field(default="CC", description="CC, IM u OFICIO")
    prefijo: str = Field(default="CNM-CC-PR", description="Prefijo oficial")
    cliente: Optional[str] = Field(default="", description="Nombre de la empresa o cliente")
    instrumento: Optional[str] = Field(default="", description="Nombre del instrumento de medición")
    metrologo: Optional[str] = Field(default="", description="Nombre del metrólogo responsable")
    locacion_id: Optional[str] = Field(default="Locación Remota", description="Identificador de la locación")
    api_key: Optional[str] = Field(default=None, description="API Key si no se envía por cabecera")

class ConfirmarConsecutivoReq(BaseModel):
    id_reserva: str = Field(..., description="ID de reserva devuelto al solicitar consecutivo")
    folio: str = Field(..., description="Folio oficial reservado")
    hash_sha256: str = Field(..., description="Hash SHA-256 del PDF final generado en la locación")
    no_servicio: Optional[str] = Field(default="", description="Número de servicio")
    total_hojas: Optional[int] = Field(default=1, description="Número total de páginas del PDF")
    api_key: Optional[str] = Field(default=None, description="API Key si no se envía por cabecera")

class CancelarConsecutivoReq(BaseModel):
    id_reserva: str = Field(..., description="ID de reserva a cancelar")
    motivo: str = Field(default="Cancelación automática por error en locación emisora")
    api_key: Optional[str] = Field(default=None, description="API Key si no se envía por cabecera")

class AjustarConsecutivoReq(BaseModel):
    area_codigo: str = "740"
    ano: int = 2026
    tipo_documento: str = "CC"
    nuevo_valor: int

class NuevaApiKeyReq(BaseModel):
    nombre_locacion: str
    api_key: Optional[str] = None


# -------------------------------------------------------------
# DEPENDENCIAS DE SEGURIDAD
# -------------------------------------------------------------
def autenticar_peticion(request: Request, x_api_key: Optional[str] = Header(None)) -> str:
    """Verifica la API Key en cabecera HTTP o query params."""
    key = x_api_key or request.query_params.get("api_key")
    if not key or not db.verificar_api_key(key):
        raise HTTPException(status_code=401, detail="API Key no autorizada o inactiva.")
    return key


# -------------------------------------------------------------
# RUTAS DE INTERFAZ WEB (DASHBOARD CENTRAL)
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard_principal(request: Request):
    """Muestra el panel web institucional con estadísticas, padrón y ajustes."""
    stats = db.obtener_resumen_estadisticas()
    registros = db.obtener_padron(limit=250)
    api_keys = db.listar_api_keys()

    # Extraer siguientes folios para CC e IM
    sig_cc = 459
    sig_im = 1
    for c in stats.get("contadores", []):
        if c["tipo_documento"] == "CC":
            sig_cc = c["consecutivo_actual"]
        elif c["tipo_documento"] == "IM":
            sig_im = c["consecutivo_actual"]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "registros": registros,
        "api_keys": api_keys,
        "sig_cc": sig_cc,
        "sig_im": sig_im
    })


# -------------------------------------------------------------
# ENDPOINTS REST API DE CONSECUTIVOS
# -------------------------------------------------------------
@app.get("/health")
def health_check():
    """Endpoint de salud del servicio (Cloud Run / Render)."""
    return {
        "status": "ok",
        "servicio": "CENAM Central Consecutivos y Padrón",
        "version": "1.0.0",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/v1/ping")
def ping_servicio(request: Request):
    """Endpoint ligero para verificar latencia y conectividad desde la aplicación de escritorio."""
    return {
        "success": True,
        "mensaje": "Conexión exitosa con el Servidor Central de Consecutivos CENAM.",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ip_cliente": request.client.host if request.client else ""
    }

@app.post("/api/v1/consecutivos/solicitar")
def api_solicitar_consecutivo(req: SolicitarConsecutivoReq, request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Reserva atómicamente el siguiente folio consecutivo para una locación remota.
    """
    key = x_api_key or req.api_key
    if not key or not db.verificar_api_key(key):
        return JSONResponse(status_code=401, content={"error": "API Key inválida o no proporcionada."})

    client_ip = request.client.host if request.client else ""
    try:
        resultado = db.solicitar_consecutivo_atomico(
            area_codigo=req.area_codigo,
            ano=req.ano,
            tipo_documento=req.tipo_documento,
            prefijo=req.prefijo,
            cliente=req.cliente,
            instrumento=req.instrumento,
            metrologo=req.metrologo,
            locacion_id=req.locacion_id,
            ip=client_ip
        )
        return resultado
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Fallo al asignar consecutivo atómico: {str(e)}"})

@app.post("/api/v1/consecutivos/confirmar")
def api_confirmar_consecutivo(req: ConfirmarConsecutivoReq, request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Confirma la emisión exitosa del documento y vincula el Hash SHA-256 en el Padrón Central.
    """
    key = x_api_key or req.api_key
    if not key or not db.verificar_api_key(key):
        return JSONResponse(status_code=401, content={"error": "API Key inválida o no proporcionada."})

    client_ip = request.client.host if request.client else ""
    resultado = db.confirmar_consecutivo(
        id_reserva=req.id_reserva,
        folio=req.folio,
        hash_sha256=req.hash_sha256,
        no_servicio=req.no_servicio,
        total_hojas=req.total_hojas,
        ip=client_ip
    )
    if not resultado.get("success"):
        return JSONResponse(status_code=400, content=resultado)
    return resultado

@app.post("/api/v1/consecutivos/cancelar")
def api_cancelar_consecutivo(req: CancelarConsecutivoReq, request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Registra la cancelación de una reserva en caso de error o interrupción en la locación remota.
    """
    key = x_api_key or req.api_key
    if not key or not db.verificar_api_key(key):
        return JSONResponse(status_code=401, content={"error": "API Key inválida o no proporcionada."})

    client_ip = request.client.host if request.client else ""
    resultado = db.cancelar_consecutivo(
        id_reserva=req.id_reserva,
        motivo=req.motivo,
        ip=client_ip
    )
    return resultado

@app.get("/api/v1/padron/resumen")
def api_resumen_padron():
    """Devuelve el conteo general de folios emitidos y contadores actuales."""
    return db.obtener_resumen_estadisticas()

@app.get("/api/v1/padron/exportar")
def exportar_padron_csv():
    """Exporta el Padrón Central completo a un archivo CSV con formato UTF-8 BOM para Excel."""
    registros = db.obtener_padron(limit=5000)

    output = io.StringIO()
    output.write('\ufeff')  # BOM para Excel
    writer = csv.writer(output)

    writer.writerow([
        "Folio Oficial",
        "Tipo",
        "Área",
        "Año",
        "Consecutivo",
        "Locación Emisora",
        "Cliente",
        "Instrumento",
        "Metrólogo",
        "No. Servicio",
        "Total Hojas",
        "Hash SHA-256",
        "Estado",
        "Fecha Reserva",
        "Fecha Confirmación"
    ])

    for r in registros:
        writer.writerow([
            r["folio"],
            r["tipo_documento"],
            r["area_codigo"],
            r["ano"],
            r["consecutivo"],
            r["locacion_id"],
            r["cliente"],
            r["instrumento"],
            r["metrologo"],
            r["no_servicio"] or "",
            r["total_hojas"] or 1,
            r["hash_sha256"] or "",
            r["estado"],
            r["fecha_reserva"],
            r["fecha_confirmacion"] or ""
        ])

    csv_data = output.getvalue()
    filename = f"Padron_Central_CENAM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/v1/admin/ajustar-consecutivo")
def api_ajustar_consecutivo(req: AjustarConsecutivoReq):
    """Permite ajustar administrativamente el número inicial o siguiente del contador."""
    exito = db.ajustar_consecutivo(
        area_codigo=req.area_codigo,
        ano=req.ano,
        tipo_documento=req.tipo_documento,
        nuevo_valor=req.nuevo_valor
    )
    return {"success": exito}

@app.post("/api/v1/admin/api-keys")
def api_crear_api_key(req: NuevaApiKeyReq):
    """Registra una nueva API Key para autorizar una locación remota."""
    if not req.nombre_locacion.strip():
        return JSONResponse(status_code=400, content={"error": "Debe especificar el nombre de la locación."})
    key = db.crear_api_key(req.nombre_locacion, req.api_key)
    return {"success": True, "api_key": key}


if __name__ == "__main__":
    import uvicorn
    # Arranque por defecto en 0.0.0.0 en el puerto 8001
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("main_consecutivos:app", host="0.0.0.0", port=port, reload=True)

