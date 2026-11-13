# Integración EPG Claro Paraguay

El repositorio mantiene su EPG XMLTV actual y añade los 10 canales seleccionados de Claro. Se ejecuta cada seis horas.

## Activación

1. Subir el contenido de `epg-main` a tu repositorio GitHub.
2. En **Settings > Secrets and variables > Actions**, crear `CLARO_EPG_SOURCE_URL` con una URL EPG autorizada, vigente y con acceso permitido para automatización. No colocar cookies ni contraseñas en archivos públicos.
3. Ejecutar **Actions > Actualizar EPG > Run workflow**.
4. Comprobar `epg/epg.json`.

**Limitación:** Claro puede requerir sesión y `epg_version` actualizados; este proyecto NO renueva credenciales, NO obtiene tokens, ni garantiza que una URL de navegador siga funcionando. El script cambia `date_from` y `date_to` a una ventana de 36 horas, pero la API puede necesitar otros parámetros vigentes. Si falla, conserva la última programación disponible.

## Prueba local

`python epg/update_claro.py archivo_respuesta_claro.json`

La prueba local acepta respuestas históricas. En ejecución automática solo acepta programas recientes. No subas respuestas originales con información de sesión a GitHub.

Los nombres de salida son `GEN.py`, `Trece.py`, `Paravision.py`, `SurTV.py`, `Venus Media.py`, `Venus.py`, `Ñanduti.py`, `America Paraguay.py`, `Popu TV.py`, `HEI.py`. HEI NOW no está confirmado como la misma señal que HEI.
