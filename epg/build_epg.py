#!/usr/bin/env python3
"""Genera epg.json a partir del XMLTV de SurTV, sin alterar las horas."""
import gzip
import io
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

SOURCE_URL = "https://raw.githubusercontent.com/lpiriz-oss/SurTV-relases/refs/heads/main/epg/guide.xml"
AQUI = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(AQUI, "epg_ids.txt")
OUT_FILE = os.path.join(AQUI, "epg.json")
HORAS_ATRAS = 3
HORAS_ADELANTE = 36
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
    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)
    return io.BytesIO(datos)


def a_epoch(texto):
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
            if fin > desde and ini < hasta and titulo and titulo.lower() not in RELLENO:
                canales[cid].append([ini, fin, titulo, detalle])
        el.clear()
    for lista in canales.values():
        lista.sort(key=lambda p: p[0])
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"generado": ahora, "canales": canales}, f, ensure_ascii=False, separators=(",", ":"))
    con_datos = sum(1 for l in canales.values() if l)
    print(f"Listo: {con_datos}/{len(ids)} canales con programación -> {OUT_FILE}")
    for cid, lista in sorted(canales.items()):
        print(f"  {cid}: {len(lista)} programas")


if __name__ == "__main__":
    main()
