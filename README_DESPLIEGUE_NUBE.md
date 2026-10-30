# CENAM - Servidor Central de Consecutivos y Padrón Metrológico
## Guía Rápida de Despliegue en la Nube o Servidor Local

Este microservicio independiente centraliza los folios consecutivos (`CNM-CC-...`, `CNM-IM-...` y Oficios) para permitir que múltiples locaciones de un área metrológica emitan certificados sin riesgo de colisión ni saltos numéricos, manteniendo un **Padrón Central de Auditoría (ISO/IEC 17025)** con los hashes SHA-256 de cada documento.

---

### Opción 1: Despliegue en Render.com (Recomendada - Gratuito y en 3 minutos)

Render permite hospedar microservicios web gratuitos con certificado SSL automático (HTTPS):

1. Cree una cuenta gratuita en [render.com](https://render.com).
2. En el panel principal, haga clic en **New +** y seleccione **Web Service**.
3. Conecte su repositorio (o suba esta carpeta a GitHub / GitLab).
4. Configure los parámetros:
   - **Name:** `cenam-consecutivos-flujo`
   - **Environment:** `Python 3` (o `Docker`)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main_consecutivos:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
5. Haga clic en **Deploy Web Service**.
6. Render le proporcionará una URL pública segura, por ejemplo:
   `https://cenam-consecutivos-flujo.onrender.com`

---

### Opción 2: Despliegue en Google Cloud Run (Serverless Institucional)

Google Cloud Run es gratuito para hasta 2 millones de peticiones al mes y escala a cero cuando no hay actividad:

1. Instale la herramienta `gcloud` y autentíquese:
   ```bash
   gcloud auth login
   gcloud config set project [SU_PROYECTO_GCP]
   ```
2. Desde la carpeta `servidor_consecutivos/`, ejecute:
   ```bash
   gcloud run deploy cenam-consecutivos --source . --region us-central1 --allow-unauthenticated
   ```
3. Cloud Run compilará el `Dockerfile` y le devolverá la URL pública HTTPS:
   `https://cenam-consecutivos-xxxx-uc.a.run.app`

---

### Opción 3: Servidor Local o PC Dedicada en el Laboratorio

Si dispone de una computadora siempre encendida con acceso a red local o IP pública:

1. Ejecute el archivo de inicio:
   ```cmd
   iniciar_servidor_consecutivos.bat
   ```
2. El servidor iniciará en:
   `http://0.0.0.0:8001`
3. Puede acceder al panel administrativo desde su navegador en:
   `http://localhost:8001`

---

### Cómo Conectar las Locaciones Remotas

Una vez que el servidor esté en línea:
1. Abra el panel administrativo web en el navegador.
2. En **Configuración Central**, cree una API Key para la nueva locación (o use la predeterminada `CENAM-DEFAULT-KEY-2026`).
3. En la computadora de la locación remota:
   - Abra el **Sistema de Certificados CENAM**.
   - Vaya a la pestaña **Configuración** $\rightarrow$ **Parámetros Generales**.
   - Seleccione **Modo Nube Centralizado (Multilocación)**.
   - Ingrese la **URL del Servidor Central** (ej. `https://cenam-consecutivos-flujo.onrender.com`), la **API Key** y el **Nombre de la Locación**.
   - Presione **Probar Conexión con Servidor**.
4. ¡Listo! A partir de ese momento, cada certificado emitido en esa locación solicitará su consecutivo a la nube y confirmará su hash de integridad automáticamente.

