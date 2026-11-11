
#!/usr/bin/env python3
"""Genera el EPG de GOAT TV utilizando únicamente SurTV."""

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

RELLENO = {"sin informacion", "sin información"}


def leer_ids():
    with open(IDS_FILE, encoding="utf-8") as f:
        return {
            linea.strip()
            for linea in f
            if linea.strip()
            and not linea.lstrip().startswith("#")
        }


def descargar(origen):
    if origen:
        with open(origen, "rb") as f:
            datos = f.read()
    else:
        req = urllib.request.Request(
            SOURCE_URL,
            headers={"User-Agent": "GOAT-TV-EPG/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = r.read()

    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)

    return io.BytesIO(datos)


def a_epoch(texto):
    return int(
        datetime.strptime(
            texto.strip(), "%Y%m%d%H%M%S %z"
        ).timestamp()
    )


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else None

    ids = leer_ids()
    ahora = int(time.time())

    desde = ahora - HORAS_ATRAS * 3600
    hasta = ahora + HORAS_ADELANTE * 3600

    canales = {cid: [] for cid in ids}

    contador = 0

    for _, el in ET.iterparse(
        descargar(origen), events=("end",)
    ):
        if el.tag != "programme":
            continue

        cid = el.get("channel")

        if cid in canales:
            try:
                ini = a_epoch(el.get("start"))
                fin = a_epoch(el.get("stop"))
            except (ValueError, TypeError, AttributeError):
                el.clear()
                continue

            titulo = (el.findtext("title") or "").strip()
            detalle = (
                el.findtext("category") or ""
            ).strip()[:80]

            if (
                fin > desde
                and ini < hasta
                and titulo
                and titulo.lower() not in RELLENO
            ):
                canales[cid].append([
                    ini, fin, titulo, detalle
                ])
                contador += 1

        el.clear()

    for cid, lista in canales.items():
        lista.sort(key=lambda p: (p[0], p[1], p[2]))

        unicos = []
        vistos = set()

        for programa in lista:
            clave = (
                programa[0],
                programa[1],
                programa[2]
            )

            if clave not in vistos:
                vistos.add(clave)
                unicos.append(programa)

        canales[cid] = unicos

    temporal = OUT_FILE + ".tmp"

    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generado": ahora,
                "canales": canales
            },
            f,
            ensure_ascii=False,
            separators=(",", ":")
        )

    os.replace(temporal, OUT_FILE)

    con_datos = sum(
        bool(lista) for lista in canales.values()
    )

    print(f"SurTV: {contador} programas encontrados")
    print(
        f"Listo: {con_datos}/{len(ids)} "
        f"canales con programación"
    )


if __name__ == "__main__":
    main()
