#!/usr/bin/env python3
"""Combina XMLTV de SurTV con cuatro canales paraguayos de TV Guide API."""
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

SOURCE_URL = "https://raw.githubusercontent.com/lpiriz-oss/SurTV-relases/refs/heads/main/epg/guide.xml"
AQUI = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(AQUI, "epg_ids.txt")
OUT_FILE = os.path.join(AQUI, "epg.json")
HORAS_ATRAS = 3
HORAS_ADELANTE = 36
RELLENO = {"sin informacion", "sin información"}

# Clave: ID interno para el epg.json; valor: ID real de TV Guide API.
CANALES_TVG = {
    "ABCTV.py": "ch_9emm5b0m",
    "Trece.py": "ch_e8q3r36y",
    "Paravision.py": "ch_jx7yjqqa",
    "SurTVItapua.py": "ch_yqjfge7a",
}


def leer_ids():
    with open(IDS_FILE, encoding="utf-8") as f:
        return {linea.strip() for linea in f if linea.strip() and not linea.lstrip().startswith("#")}


def descargar(origen):
    if origen:
        with open(origen, "rb") as f:
            datos = f.read()
    else:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "GOAT-TV-EPG/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = r.read()
    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)
    return io.BytesIO(datos)


def a_epoch(texto):
    return int(datetime.strptime(texto.strip(), "%Y%m%d%H%M%S %z").timestamp())


def a_epoch_iso(texto):
    return int(datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp())


def cargar_surtv(origen, canales, desde, hasta):
    # Si la descarga falla, no se publica un EPG nuevo vacío.
    contador = 0
    for _, el in ET.iterparse(descargar(origen), events=("end",)):
        if el.tag != "programme":
            continue
        cid = el.get("channel")
        if cid in canales:
            try:
                ini, fin = a_epoch(el.get("start")), a_epoch(el.get("stop"))
            except (ValueError, TypeError, AttributeError):
                el.clear()
                continue
            titulo = (el.findtext("title") or "").strip()
            detalle = (el.findtext("category") or "").strip()[:80]
            if fin > desde and ini < hasta and titulo and titulo.lower() not in RELLENO:
                canales[cid].append([ini, fin, titulo, detalle])
                contador += 1
        el.clear()
    print(f"SurTV: {contador} programas cargados")


def pedir_json(url, clave):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {clave}",
        "Accept": "application/json",
        "User-Agent": "GOAT-TV-EPG/1.0",
    })
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.load(resp)


def cargar_tvg(canales, desde, hasta):
    clave = os.environ.get("TVG_API_KEY", "").strip()
    if not clave:
        print("TV Guide API: sin TVG_API_KEY; se conserva únicamente SurTV")
        return

    inicio_dia = datetime.fromtimestamp(desde, timezone.utc).date()
    fin_dia = datetime.fromtimestamp(hasta - 1, timezone.utc).date()
    dias = [(inicio_dia + timedelta(days=i)).isoformat()
            for i in range((fin_dia - inicio_dia).days + 1)]

    for interno, api_id in CANALES_TVG.items():
        if interno not in canales:
            continue
        encontrados = 0
        # La API usa paginación; se respeta meta.next / meta.next_cursor.
        for dia in dias:
            cursor = None
            vistos = set()
            for _ in range(30):
                parametros = {"date": dia}
                if cursor:
                    parametros["cursor"] = cursor
                url = (f"https://api.tvguideapi.com/v1/channels/{api_id}/schedule?"
                       + urllib.parse.urlencode(parametros))
                try:
                    respuesta = pedir_json(url, clave)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
                    print(f"TVG {interno} {dia}: consulta fallida ({exc})")
                    break
                for programa in respuesta.get("data", []):
                    try:
                        ini = a_epoch_iso(programa["start"])
                        fin = a_epoch_iso(programa["stop"])
                        titulo = str(programa.get("title") or "").strip()
                        categoria = programa.get("category") or []
                        detalle = (str(categoria[0]) if isinstance(categoria, list) and categoria
                                   else str(categoria) if isinstance(categoria, str) else "")[:80]
                        if fin > desde and ini < hasta and titulo and titulo.lower() not in RELLENO:
                            canales[interno].append([ini, fin, titulo, detalle])
                            encontrados += 1
                    except (KeyError, TypeError, ValueError, AttributeError):
                        continue
                meta = respuesta.get("meta") or {}
                siguiente = meta.get("next_cursor") or meta.get("next")
                if not siguiente or siguiente in vistos:
                    break
                vistos.add(siguiente)
                cursor = siguiente
        print(f"TVG {interno}: {encontrados} programas recibidos")


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else None
    ids = leer_ids()
    ahora = int(time.time())
    desde = ahora - HORAS_ATRAS * 3600
    hasta = ahora + HORAS_ADELANTE * 3600
    canales = {cid: [] for cid in ids}

    cargar_surtv(origen, canales, desde, hasta)
    cargar_tvg(canales, desde, hasta)

    for cid, lista in canales.items():
        lista.sort(key=lambda p: (p[0], p[1], p[2]))
        unicos = []
        vistos = set()
        for programa in lista:
            clave = (programa[0], programa[1], programa[2])
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(programa)
        canales[cid] = unicos

    # Escritura atómica para no dejar un archivo incompleto.
    temporal = OUT_FILE + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump({"generado": ahora, "canales": canales}, f,
                  ensure_ascii=False, separators=(",", ":"))
    os.replace(temporal, OUT_FILE)
    con_datos = sum(bool(lista) for lista in canales.values())
    print(f"Listo: {con_datos}/{len(ids)} canales con programación -> {OUT_FILE}")
    for cid in sorted(CANALES_TVG):
        if cid in canales:
            print(f"  {cid}: {len(canales[cid])} programas")


if __name__ == "__main__":
    main()
