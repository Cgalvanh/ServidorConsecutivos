# Imagen ligera oficial de Python para producción
FROM python:3.12-slim

# Metadatos
LABEL maintainer="CENAM - Centro Nacional de Metrología"
LABEL description="Microservicio Central de Consecutivos y Padrón Metrológico"

# Variables de entorno para Python optimizado
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8001

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiar dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Exponer puerto configurado
EXPOSE 8001

# Comando de inicio compatible con Cloud Run, Render y VPS
CMD uvicorn main_consecutivos:app --host 0.0.0.0 --port ${PORT}

