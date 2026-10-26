# Observatorio de noticias · Grupo Boryszew

Aplicación web en español para investigar noticias públicas de Boryszew y Maflow, consultar el historial y visualizar o descargar informes PDF. Incluye generación manual y programación diaria **a las 08:00, Europe/Madrid**, configurable desde la pantalla.

[Descargar aplicación ZIP](dist/observatorio-boryszew.zip) · Extrae el paquete y consulta `LEEME-PRIMERO.txt`.

## Puesta en marcha

Requiere Python 3.12 o posterior. Las fuentes DejaVu se distribuyen en `assets/fonts/` con su licencia. Para las pruebas de extracción del PDF también se necesita `pdftotext` (`poppler-utils` en Debian/Ubuntu). La aplicación y el lanzador se han validado en Linux; se incluyen accesos de arranque para Windows y macOS pendientes de prueba en esos sistemas.

### Abrir la interfaz en tu ordenador

Extrae el paquete `observatorio-boryszew.zip` en una carpeta e instala Python 3.12 o posterior si no lo tienes. Después:

- **Windows:** abre `iniciar.bat`.
- **macOS o Linux:** ejecuta `bash iniciar.command` desde la carpeta extraída.
- **Cualquier sistema:** también puedes ejecutar `python launch.py` con Python 3.12 o posterior.

El lanzador prepara las dependencias y abre la interfaz en tu navegador. La primera ejecución necesita Internet para descargar paquetes. Mantén la ventana del lanzador abierta; al cerrarlo se detiene el servicio. No incluye una clave de IA: al abrir el panel, introduce tu clave de OpenAI en **Conexión de IA** y pulsa **Guardar conexión** para redactar noticias en español. Como alternativa, configura `NEWS_LLM_API_KEY` en el entorno antes de iniciarlo. El horario se mantiene a las 08:00 de Madrid y puede editarse desde la pantalla.

Esta es una aplicación local, no una web publicada. Para abrirla desde otros dispositivos o acceder mediante un dominio hace falta desplegarla en un alojamiento con HTTPS y control de acceso.

### Diseño de la interfaz

El panel incluye navegación, generación manual, resumen de configuración, programación, historial, estado de la IA y lectura/descarga del informe. Los colores están centralizados en los tokens de `static/style.css`. La paleta se ha contrastado con las hojas de estilo de `maflow.com`: azul oscuro `#282744`, burdeos `#8E1F29`, rojo `#C90E19`, gris `#A5A4AD`, fondo `#F0F0F2` y blanco. Se utiliza el logotipo publicado por Maflow, conservando su relación de aspecto. Consulta la procedencia en `docs/identidad-visual.md`.

### Arranque manual

Desde `/workspace/REPO_SITES_CODEX/agente-noticias-boryszew`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python app.py
```

El servicio escucha en el puerto 8000 y, por defecto, solo en la interfaz local. `GET /health` permite comprobar el arranque. Abre la aplicación mediante el mecanismo de acceso de tu alojamiento; la configuración del entorno de onboarding no publica una web.

Antes de generar informes con noticias, conecta tu clave de OpenAI desde **Conexión de IA** en la aplicación local, o configura **`NEWS_LLM_API_KEY`** en el gestor seguro de variables o secretos del alojamiento. Se usa la API de OpenAI para traducir y resumir; las peticiones pueden tener coste según tu cuenta. También se admite una variable `OPENAI_API_KEY` ya existente. Nunca introduzcas claves en el chat ni las subas a Git. `.env.example` documenta las variables; la aplicación no carga archivos `.env` automáticamente.

### Variables

| Variable | Uso | Valor por defecto |
| --- | --- | --- |
| `NEWS_LLM_API_KEY` | Credencial de OpenAI para la redacción en español | Obligatoria si hay noticias |
| `NEWS_LLM_MODEL` | Modelo compatible con Chat Completions y JSON | `gpt-4o-mini` |
| `NEWS_RSS_URLS` | Canales RSS 2.0 adicionales, HTTPS, separados por comas | Ninguno |
| `NEWS_DATA_DIR` | Directorio persistente de SQLite y clave de sesión | `data/` dentro del proyecto |
| `NEWS_HOST` | Interfaz de escucha | `127.0.0.1` |
| `PORT` | Puerto HTTP | `8000` |

Permite salida HTTPS a `news.google.com` y `api.openai.com`. Si añades canales RSS, permite también sus destinos y posibles redirecciones. No se desactiva la verificación TLS.

## Uso

1. Pulsa **Generar informe** para investigar las últimas 24 horas. La investigación se ejecuta en segundo plano y la pantalla se actualiza mientras trabaja.
2. Consulta el resumen del día y cada noticia con su fecha, fuente, resumen español y enlace. El titular original está disponible como referencia.
3. Elige **Visualizar PDF** o **Descargar PDF**. El PDF incorpora el periodo, las noticias, enlaces pulsables, cobertura y limitaciones.
4. Ajusta el horario o desactiva la generación automática en **Programación diaria**. La zona `Europe/Madrid` contempla los cambios de horario de verano.
5. Consulta los informes y errores anteriores en **Historial**. La interfaz muestra las últimas 60 investigaciones; los registros anteriores siguen en SQLite.

## Qué investiga y cuáles son sus límites

Por defecto consulta Google News RSS en inglés y polaco para Boryszew y Maflow, además de búsquedas de comunicaciones de `boryszew.com.pl` y publicaciones públicas de `linkedin.com` indexadas por Google News. **No es una integración con LinkedIn ni garantiza encontrar sus publicaciones**: Google News puede no indexarlas y devolver cero resultados. No se inicia sesión ni se accede a contenido privado. Para cobertura específica de LinkedIn hace falta incorporar una fuente autorizada que suministre sus publicaciones; esta versión solo ofrece búsqueda pública indexada.

Los informes se basan en **titulares y extractos indexados**, no en la lectura íntegra de las noticias ni en rastreo directo de todas las empresas del grupo. Pueden incorporar otras fuentes mediante `NEWS_RSS_URLS`. Solo se admiten elementos RSS 2.0 con fecha de publicación verificable dentro de las últimas 24 horas. No se considera la fecha de consulta como fecha de publicación. El enlace puede ser de Google News y redirigir al medio original.

Se eliminan duplicados por URL y titular normalizados y se incluyen hasta 25 noticias, priorizando las más recientes. Distintos medios que describan el mismo acontecimiento pueden seguir apareciendo por separado. Los resultados adicionales omitidos se indican. Los contenidos externos se envían como datos a la IA, que debe redactar en español sin completar hechos ausentes; la aplicación valida el formato y los identificadores y conserva las fuentes originales. Conviene revisar la redacción automática para decisiones importantes.

Si falla un canal, se muestra como cobertura incompleta. Si fallan todos, la ejecución termina con error y **no** se publica un informe que afirme que no hay noticias. Si las consultas responden pero no encuentran publicaciones fechadas en el periodo, se genera un informe explícito de cero resultados sin llamar a la IA. La aplicación no inventa resúmenes si falta la clave o falla el proveedor.

## Ejecución diaria y alojamiento

El programador está integrado en `app.py`, usa un único proceso de Waitress y comprueba el horario cada 20 segundos. El informe comienza a la hora configurada; el tiempo de consulta y redacción depende de los servicios externos. Los informes automáticos quedan disponibles en la aplicación; no se envían por correo.

**El servicio debe permanecer encendido en un alojamiento permanente** para trabajar cada día. Una sesión de desarrollo o una máquina de Codex suspendida no constituye un alojamiento permanente. Usa un supervisor o contenedor con reinicio automático y monta `NEWS_DATA_DIR` en almacenamiento persistente. No ejecutes varios procesos con los mismos datos: el servicio utiliza un bloqueo de instancia y SQLite evita investigaciones simultáneas.

Tras reiniciar, las investigaciones interrumpidas se marcan como error. Si aún no existe ejecución automática de hoy y ya pasó su hora, se lanza una investigación de las últimas 24 horas. No se recuperan días anteriores. Un fallo automático no se reintenta indefinidamente el mismo día: corrige la causa y usa la generación manual. Cambiar el horario no repite una ejecución automática ya registrada para hoy.

La aplicación está pensada para uso privado y no incluye cuentas de usuario. Antes de exponerla a Internet, sitúala detrás de un proxy con HTTPS y autenticación. Todos los usuarios con acceso a la aplicación comparten informes y programación. Las claves se configuran desde el panel local o en el entorno del servidor; no se devuelven al navegador. La clave introducida en el panel se guarda sin cifrar en `data/llm.key`, con permisos restringidos a tu usuario en Linux/macOS; en Windows depende de los permisos de la carpeta. Usa un ordenador de confianza. Puedes borrarla desde el mismo panel. Una variable de entorno existente tiene prioridad sobre la clave local.

## Desarrollo y pruebas

```bash
.venv/bin/python -m pytest -q
```

`requirements.lock` fija las dependencias directas y transitivas, incluidas las de pruebas. `requirements.txt` y `requirements-dev.txt` describen los grupos de dependencias. Las pruebas verifican fechas, errores de fuentes, deduplicación, validación de respuestas de IA, persistencia, ejecución manual y diaria, horario de verano, formularios y PDF con caracteres españoles y polacos. Usan datos de prueba y respuestas simuladas; no sustituyen una comprobación real de fuentes y proveedor con conectividad y credenciales válidas.

## Estructura

```text
app.py              # Interfaz HTTP, formularios y arranque
launch.py           # Preparación local y apertura del navegador
iniciar.bat         # Acceso de arranque para Windows
iniciar.command     # Acceso de arranque para macOS/Linux
news.py             # Fuentes RSS y redacción con IA
worker.py           # Generación en segundo plano y programación diaria
store.py            # Persistencia SQLite
reports.py          # PDF con enlaces y fuentes Unicode
templates/          # Pantalla en español
static/             # Estilos adaptables y actualización del estado
assets/fonts/       # Fuentes PDF y licencia de distribución
tests/              # Pruebas automatizadas
data/               # Datos locales ignorados por Git
```
