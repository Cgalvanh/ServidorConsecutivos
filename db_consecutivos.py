#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Base de Datos y Control Atómico de Consecutivos - CENAM
======================================================
Gestiona la secuencia de folios y el Padrón Central de Certificados, Informes
y Oficios para múltiples locaciones simultáneas mediante bloqueos atómicos
y modo WAL (Write-Ahead Logging).
"""

import os
import sqlite3
import secrets
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cenam_consecutivos_padron.db")

# Candado en memoria para asegurar serialización de transacciones concurrentes
_DB_LOCK = threading.Lock()

def get_connection():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Optimización para alto rendimiento y lecturas/escrituras concurrentes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Inicializa la estructura de tablas para contadores, padrón y llaves de acceso."""
    with _DB_LOCK:
        conn = get_connection()
        c = conn.cursor()

        # 1. Tabla de Contadores Atómicos por Área, Año y Tipo
        c.execute("""
        CREATE TABLE IF NOT EXISTS contadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_codigo TEXT NOT NULL,
            ano INTEGER NOT NULL,
            tipo_documento TEXT NOT NULL,
            prefijo TEXT NOT NULL,
            consecutivo_actual INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(area_codigo, ano, tipo_documento)
        )
        """)

        # 2. Padrón Central de Trazabilidad y Auditoría Metrológica (ISO/IEC 17025)
        c.execute("""
        CREATE TABLE IF NOT EXISTS padron_central (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_reserva TEXT UNIQUE NOT NULL,
            folio TEXT UNIQUE NOT NULL,
            tipo_documento TEXT NOT NULL,
            area_codigo TEXT NOT NULL,
            ano INTEGER NOT NULL,
            consecutivo INTEGER NOT NULL,
            cliente TEXT,
            instrumento TEXT,
            metrologo TEXT,
            locacion_id TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'RESERVADO',
            hash_sha256 TEXT,
            total_hojas INTEGER,
            no_servicio TEXT,
            motivo_cancelacion TEXT,
            fecha_reserva TEXT NOT NULL,
            fecha_confirmacion TEXT
        )
        """)

        # 3. Llaves de Acceso API para Locaciones Autorizadas
        c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_locacion TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        # 4. Bitácora Central de Operaciones
        c.execute("""
        CREATE TABLE IF NOT EXISTS bitacora_consecutivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT NOT NULL,
            locacion_id TEXT,
            ip TEXT
        )
        """)

        # Sembrar contadores por defecto si está vacía
        c.execute("SELECT COUNT(*) FROM contadores")
        if c.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # CC: Consecutivo inicial por defecto 459 (Área 740, Año 2026)
            c.execute("""
            INSERT INTO contadores (area_codigo, ano, tipo_documento, prefijo, consecutivo_actual, updated_at)
            VALUES ('740', 2026, 'CC', 'CNM-CC-PR', 459, ?)
            """, (now_str,))
            # IM: Consecutivo inicial por defecto 1
            c.execute("""
            INSERT INTO contadores (area_codigo, ano, tipo_documento, prefijo, consecutivo_actual, updated_at)
            VALUES ('740', 2026, 'IM', 'CNM-IM-PR', 1, ?)
            """, (now_str,))
            # OFICIO: Consecutivo inicial por defecto 1
            c.execute("""
            INSERT INTO contadores (area_codigo, ano, tipo_documento, prefijo, consecutivo_actual, updated_at)
            VALUES ('740', 2026, 'OFICIO', 'OFICIO', 1, ?)
            """, (now_str,))

        # Sembrar API Key institucional por defecto si no hay ninguna
        c.execute("SELECT COUNT(*) FROM api_keys")
        if c.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
            INSERT INTO api_keys (nombre_locacion, api_key, activa, created_at)
            VALUES ('Locación Matriz CENAM', 'CENAM-DEFAULT-KEY-2026', 1, ?)
            """, (now_str,))

        conn.commit()
        conn.close()

def verificar_api_key(api_key: str) -> bool:
    """Verifica si la API Key proporcionada es válida y activa."""
    if not api_key:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM api_keys WHERE api_key = ? AND activa = 1", (api_key.strip(),))
    row = c.fetchone()
    conn.close()
    return row is not None

def solicitar_consecutivo_atomico(
    area_codigo: str,
    ano: int,
    tipo_documento: str,
    prefijo: str,
    cliente: Optional[str] = "",
    instrumento: Optional[str] = "",
    metrologo: Optional[str] = "",
    locacion_id: Optional[str] = "Locación Remota",
    ip: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Reserva un número consecutivo de manera estrictamente atómica.
    Garantiza que dos peticiones concurrentes jamás reciban el mismo número.
    """
    tipo_doc = tipo_documento.strip().upper()
    prefijo_clean = prefijo.strip()
    area_clean = area_codigo.strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _DB_LOCK:
        conn = get_connection()
        conn.isolation_level = None  # Autocommit off para usar transacciones explícitas
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")

        try:
            # 1. Obtener o inicializar el contador
            c.execute("""
                SELECT id, consecutivo_actual, prefijo
                FROM contadores
                WHERE area_codigo = ? AND ano = ? AND tipo_documento = ?
            """, (area_clean, ano, tipo_doc))
            row = c.fetchone()

            if row:
                consecutivo_asignado = row["consecutivo_actual"]
                nuevo_consecutivo = consecutivo_asignado + 1
                c.execute("""
                    UPDATE contadores
                    SET consecutivo_actual = ?, prefijo = ?, updated_at = ?
                    WHERE id = ?
                """, (nuevo_consecutivo, prefijo_clean, now_str, row["id"]))
            else:
                consecutivo_asignado = 1
                nuevo_consecutivo = 2
                c.execute("""
                    INSERT INTO contadores (area_codigo, ano, tipo_documento, prefijo, consecutivo_actual, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (area_clean, ano, tipo_doc, prefijo_clean, nuevo_consecutivo, now_str))

            # 2. Construir folio oficial
            folio = f"{prefijo_clean}-{area_clean}-{consecutivo_asignado:03d}-{ano}"
            id_reserva = f"res_{secrets.token_hex(12)}"

            # 3. Registrar en Padrón Central con estado 'RESERVADO'
            c.execute("""
                INSERT INTO padron_central (
                    id_reserva, folio, tipo_documento, area_codigo, ano, consecutivo,
                    cliente, instrumento, metrologo, locacion_id, estado, fecha_reserva
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVADO', ?)
            """, (
                id_reserva, folio, tipo_doc, area_clean, ano, consecutivo_asignado,
                cliente or "", instrumento or "", metrologo or "", locacion_id or "Locación Remota",
                now_str
            ))

            # 4. Registrar en bitácora
            c.execute("""
                INSERT INTO bitacora_consecutivos (timestamp, accion, detalle, locacion_id, ip)
                VALUES (?, 'RESERVA_FOLIO', ?, ?, ?)
            """, (now_str, f"Folio {folio} ({tipo_doc}) reservado para '{cliente}' por {metrologo}.", locacion_id, ip))

            c.execute("COMMIT")
            conn.close()

            return {
                "success": True,
                "consecutivo": consecutivo_asignado,
                "folio": folio,
                "id_reserva": id_reserva,
                "tipo_documento": tipo_doc,
                "expira_en_segundos": 300
            }

        except Exception as e:
            c.execute("ROLLBACK")
            conn.close()
            raise e

def confirmar_consecutivo(
    id_reserva: str,
    folio: str,
    hash_sha256: str,
    no_servicio: Optional[str] = "",
    total_hojas: Optional[int] = 1,
    ip: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Confirma la emisión exitosa del documento en la locación remota,
    vinculando el Hash SHA-256 de integridad al Padrón Central.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _DB_LOCK:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT id, folio, estado, locacion_id, cliente
            FROM padron_central
            WHERE id_reserva = ?
        """, (id_reserva.strip(),))
        row = c.fetchone()

        if not row:
            conn.close()
            return {"success": False, "error": f"No se encontró la reserva '{id_reserva}'."}

        if row["estado"] == "CANCELADO_NO_EMITIDO":
            conn.close()
            return {"success": False, "error": f"El folio '{row['folio']}' fue previamente cancelado y no puede ser confirmado."}

        c.execute("""
            UPDATE padron_central
            SET estado = 'CONFIRMADO',
                hash_sha256 = ?,
                no_servicio = ?,
                total_hojas = ?,
                fecha_confirmacion = ?
            WHERE id_reserva = ?
        """, (hash_sha256.strip(), no_servicio or "", total_hojas or 1, now_str, id_reserva.strip()))

        c.execute("""
            INSERT INTO bitacora_consecutivos (timestamp, accion, detalle, locacion_id, ip)
            VALUES (?, 'CONFIRMACION_FOLIO', ?, ?, ?)
        """, (now_str, f"Folio {row['folio']} confirmado exitosamente. Hash: {hash_sha256[:16]}...", row["locacion_id"], ip))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "folio": row["folio"],
            "mensaje": "Folio confirmado e inscrito en el Padrón Central Oficial de CENAM."
        }

def cancelar_consecutivo(id_reserva: str, motivo: str, ip: Optional[str] = "") -> Dict[str, Any]:
    """
    Marca un folio reservado como 'CANCELADO_NO_EMITIDO' en el Padrón Central
    para mantener la justificación de auditoría metrológica.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _DB_LOCK:
        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT id, folio, locacion_id FROM padron_central WHERE id_reserva = ?", (id_reserva.strip(),))
        row = c.fetchone()

        if not row:
            conn.close()
            return {"success": False, "error": "Reserva no encontrada."}

        c.execute("""
            UPDATE padron_central
            SET estado = 'CANCELADO_NO_EMITIDO',
                motivo_cancelacion = ?,
                fecha_confirmacion = ?
            WHERE id_reserva = ?
        """, (motivo or "Cancelación automática por error en locación emisora", now_str, id_reserva.strip()))

        c.execute("""
            INSERT INTO bitacora_consecutivos (timestamp, accion, detalle, locacion_id, ip)
            VALUES (?, 'CANCELACION_RESERVA', ?, ?, ?)
        """, (now_str, f"Folio {row['folio']} marcado como CANCELADO_NO_EMITIDO: {motivo}", row["locacion_id"], ip))

        conn.commit()
        conn.close()

        return {"success": True, "folio": row["folio"], "mensaje": "Folio cancelado registrado en auditoría."}

def obtener_resumen_estadisticas() -> Dict[str, Any]:
    """Devuelve estadísticas en tiempo real para el panel de administración central."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM padron_central")
    total_registros = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM padron_central WHERE estado = 'CONFIRMADO'")
    total_confirmados = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM padron_central WHERE estado = 'RESERVADO'")
    total_reservados = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM padron_central WHERE estado = 'CANCELADO_NO_EMITIDO'")
    total_cancelados = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT locacion_id) FROM padron_central")
    locaciones_activas = c.fetchone()[0]

    # Contadores actuales
    c.execute("SELECT area_codigo, ano, tipo_documento, prefijo, consecutivo_actual FROM contadores ORDER BY tipo_documento ASC")
    contadores = [dict(row) for row in c.fetchall()]

    conn.close()

    return {
        "total_registros": total_registros,
        "total_confirmados": total_confirmados,
        "total_reservados": total_reservados,
        "total_cancelados": total_cancelados,
        "locaciones_activas": locaciones_activas,
        "contadores": contadores
    }

def obtener_padron(
    filtro_tipo: Optional[str] = None,
    filtro_estado: Optional[str] = None,
    busqueda: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Consulta paginada del Padrón Central con filtros opcionales."""
    conn = get_connection()
    c = conn.cursor()

    query = "SELECT * FROM padron_central WHERE 1=1"
    params = []

    if filtro_tipo and filtro_tipo != "TODOS":
        query += " AND tipo_documento = ?"
        params.append(filtro_tipo)

    if filtro_estado and filtro_estado != "TODOS":
        query += " AND estado = ?"
        params.append(filtro_estado)

    if busqueda and busqueda.strip():
        term = f"%{busqueda.strip()}%"
        query += " AND (folio LIKE ? OR cliente LIKE ? OR instrumento LIKE ? OR metrologo LIKE ? OR locacion_id LIKE ?)"
        params.extend([term, term, term, term, term])

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def ajustar_consecutivo(area_codigo: str, ano: int, tipo_documento: str, nuevo_valor: int) -> bool:
    """Ajusta administrativamente el valor siguiente del consecutivo."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _DB_LOCK:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE contadores
            SET consecutivo_actual = ?, updated_at = ?
            WHERE area_codigo = ? AND ano = ? AND tipo_documento = ?
        """, (nuevo_valor, now_str, area_codigo.strip(), ano, tipo_documento.strip().upper()))
        updated = c.rowcount > 0
        conn.commit()
        conn.close()
        return updated

def listar_api_keys() -> List[Dict[str, Any]]:
    """Obtiene la lista de API keys configuradas."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nombre_locacion, api_key, activa, created_at FROM api_keys ORDER BY id ASC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def crear_api_key(nombre_locacion: str, custom_key: Optional[str] = None) -> str:
    """Registra una nueva API key para una locación remota."""
    key = custom_key.strip() if custom_key else f"CENAM-KEY-{secrets.token_hex(8).upper()}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO api_keys (nombre_locacion, api_key, activa, created_at)
        VALUES (?, ?, 1, ?)
    """, (nombre_locacion.strip(), key, now_str))
    conn.commit()
    conn.close()
    return key

