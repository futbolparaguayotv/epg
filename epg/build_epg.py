#!/usr/bin/env python3
"""
Descarga un XMLTV, se queda solo con tus canales y genera un epg.json liviano.

Uso:
    python epg/build_epg.py                      # descarga SOURCE_URL
    python epg/build_epg.py archivo.xml          # usa un XML local

Salida (epg/epg.json):
{
  "generado": 1793900000,                 # momento en que se creó (epoch, segundos)
  "canales": {
    "Gen.py": [[inicio, fin, "Título", "Detalle"], ...]
  }
}
inicio y fin son epoch en segundos (UTC), así la app no depende de zonas horarias.
"""
import gzip
import io
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Cambia esto por TU propio XMLTV cuando lo tengas.
# Si usas el de otra persona, pídele permiso primero.
SOURCE_URL = "https://raw.githubusercontent.com/lpiriz-oss/SurTV-relases/refs/heads/main/epg/guide.xml"

AQUI = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(AQUI, "epg_ids.txt")
OUT_FILE = os.path.join(AQUI, "epg.json")

HORAS_ATRAS = 3      # programas que terminaron hace menos de 3 h
HORAS_ADELANTE = 36  # programas que empiezan en las próximas 36 h
RELLENO = ("sin informacion", "sin información")


def leer_ids():
    ids = set()
    with open(IDS_FILE, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                ids.add(linea)
    return ids


def abrir_fuente(origen):
    if origen:
        with open(origen, "rb") as f:
            datos = f.read()
    else:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = r.read()
    if datos[:2] == b"\x1f\x8b":  # viene comprimido (.gz)
        datos = gzip.decompress(datos)
    return io.BytesIO(datos)


def a_epoch(texto):
    # Formato XMLTV: 20261105100000 -0300
    return int(datetime.strptime(texto.strip(), "%Y%m%d%H%M%S %z").timestamp())


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else None
    ids = leer_ids()
    ahora = int(time.time())
    desde = ahora - HORAS_ATRAS * 3600
    hasta = ahora + HORAS_ADELANTE * 3600

    canales = {i: [] for i in ids}
    for _, el in ET.iterparse(abrir_fuente(origen), events=("end",)):
        if el.tag != "programme":
            continue
        cid = el.get("channel")
        if cid in canales:
            try:
                ini, fin = a_epoch(el.get("start")), a_epoch(el.get("stop"))
            except (ValueError, TypeError):
                el.clear()
                continue
            titulo = (el.findtext("title") or "").strip()
            detalle = (el.findtext("category") or "").strip()[:80]
            if (fin > desde and ini < hasta and titulo
                    and titulo.lower() not in RELLENO):
                canales[cid].append([ini, fin, titulo, detalle])
        el.clear()  # libera memoria: el XML puede pesar varios MB

    for lista in canales.values():
        lista.sort(key=lambda p: p[0])

    # Conservar canales añadidos por Claro cuando se regenera desde XMLTV.
    claro_keys = {"GEN.py", "Trece.py", "Paravision.py", "SurTV.py",
                  "Venus Media.py", "Venus.py", "Ñanduti.py",
                  "America Paraguay.py", "Popu TV.py", "HEI.py"}
    if os.path.isfile(OUT_FILE):
        try:
            with open(OUT_FILE, encoding="utf-8") as previous:
                prev = json.load(previous).get("canales", {})
            for cid in claro_keys:
                if prev.get(cid):
                    canales[cid] = prev[cid]
        except (ValueError, OSError):
            pass

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"generado": ahora, "canales": canales}, f,
                  ensure_ascii=False, separators=(",", ":"))

    con_datos = sum(1 for l in canales.values() if l)
    print(f"Listo: {con_datos}/{len(ids)} canales con programación -> {OUT_FILE}")
    for cid, lista in sorted(canales.items()):
        print(f"  {cid}: {len(lista)} programas")


if __name__ == "__main__":
    main()
