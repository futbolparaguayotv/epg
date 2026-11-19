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
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# Cambia esto por TU propio XMLTV cuando lo tengas.
# Si usas el de otra persona, pídele permiso primero.
SOURCE_URL = "https://raw.githubusercontent.com/lpiriz-oss/SurTV-relases/refs/heads/main/epg/guide.xml"

AQUI = os.path.dirname(os.path.abspath(__file__))
IDS_FILE = os.path.join(AQUI, "epg_ids.txt")
OUT_FILE = os.path.join(AQUI, "epg.json")

HORAS_ATRAS = 3      # programas que terminaron hace menos de 3 h
HORAS_ADELANTE = 36  # programas que empiezan en las próximas 36 h
RELLENO = ("sin informacion", "sin información")

# Corrección exclusiva para los canales paraguayos de SurTV.
DESFASE_PARAGUAY = 3 * 3600
CANALES_PARAGUAY = {
    "Gen.py", "LaTele.py", "SNT.py", "Telefuturo.py",
    "NoticiasParaguay.py", "C9N.py", "canal_pro.py", "unicanal.py",
}


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


GEN_URL = "https://www.gen.com.py/"
GEN_TZ = timezone(timedelta(hours=-3))


def extraer_gen(html):
    for m in re.finditer(r'"settings"\s*:\s*', html):
        try:
            raw, _ = json.JSONDecoder().raw_decode(html[m.end():])
            datos = json.loads(raw) if isinstance(raw, str) else raw
            dias = datos.get("programacion")
            if isinstance(dias, list) and len(dias) == 5 and all(dias):
                return dias
        except (ValueError, AttributeError, TypeError):
            continue
    raise ValueError("No se encontró la programación semanal de GEN")


def programas_gen(html, desde, hasta):
    dias = extraer_gen(html)
    fecha = datetime.fromtimestamp(desde, GEN_TZ).date()
    ultima = datetime.fromtimestamp(hasta, GEN_TZ).date()
    salida = []
    while fecha <= ultima:
        if fecha.weekday() < 5:
            filas = []
            for programa in dias[fecha.weekday()]:
                hora = datetime.strptime(programa["hora_inicio"], "%H:%M").time()
                inicio = datetime.combine(fecha, hora, tzinfo=GEN_TZ)
                filas.append((inicio, programa["programa"].strip()))
            filas.sort()
            for i, (inicio, titulo) in enumerate(filas):
                # La web no publica el fin del último programa: estimar medianoche.
                fin = filas[i+1][0] if i+1 < len(filas) else datetime.combine(fecha + timedelta(days=1), datetime.min.time(), tzinfo=GEN_TZ)
                a, b = int(inicio.timestamp()), int(fin.timestamp())
                if b > desde and a < hasta and b > a and titulo:
                    salida.append([a, b, titulo, ""])
        fecha += timedelta(days=1)
    return salida


def actualizar_gen(canales, desde, hasta):
    if "Gen.py" not in canales:
        return
    try:
        req = urllib.request.Request(GEN_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8")
        oficial = programas_gen(html, desde, hasta)
        # Conservar SurTV únicamente donde no se superpone con la fuente oficial.
        respaldo = [p for p in canales["Gen.py"] if not any(p[0] < q[1] and p[1] > q[0] for q in oficial)]
        canales["Gen.py"] = oficial + respaldo
        print(f"GEN oficial: {len(oficial)} programas")
    except Exception as exc:
        print(f"GEN oficial no disponible; se conserva SurTV: {exc}")


from html.parser import HTMLParser
from urllib.error import URLError

MITV_URL = 'https://mi.tv/py/async/channel'
CANALES_MITV = {
    'Trece.py': 'canal-13',
    'ABCTV.py': 'abc-tv',
    'Hei.py': 'hei-network',
    'ParaguayTV.py': 'paraguay-tv',
    'Paravision.py': 'canal-5-paravision',
}

class TreceParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.active=False; self.row=None; self.field=None; self.heading=False; self.date_text=''
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); cls=a.get('class','').split()
        if tag=='h1': self.heading=True
        if tag=='ul' and 'broadcasts' in cls: self.active=True
        if not self.active: return
        if tag=='li': self.row={}
        if self.row is None: return
        if tag=='span' and 'time' in cls: self.field='time'
        elif tag=='h2': self.field='title'
        elif tag=='p' and 'synopsis' in cls: self.field='detail'
    def handle_data(self, data):
        if self.heading: self.date_text+=data
        if self.row is not None and self.field: self.row[self.field]=self.row.get(self.field,'')+data
    def handle_endtag(self, tag):
        if tag=='h1': self.heading=False
        if tag in ('span','h2','p'): self.field=None
        if tag=='li' and self.row is not None:
            if self.row.get('time') and self.row.get('title'): self.rows.append(self.row)
            self.row=None; self.field=None
        if tag=='ul': self.active=False

def trece_inicios(html, fecha):
    parser=TreceParser(); parser.feed(html)
    meses='enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()
    if not re.search(r'\b'+str(fecha.day)+r'\s+de\s+'+meses[fecha.month-1]+r'\b', parser.date_text.lower()):
        raise ValueError('Fecha Mi.tv inesperada: '+parser.date_text)
    filas=[]; anterior=None
    for row in parser.rows:
        hora=datetime.strptime(row['time'].strip(), '%H:%M').time()
        if anterior is not None and hora < anterior: fecha += timedelta(days=1)
        anterior=hora
        inicio=int(datetime.combine(fecha,hora,tzinfo=GEN_TZ).timestamp())
        filas.append((inicio,' '.join(row['title'].split()),' '.join(row.get('detail','').split())))
    if len(filas)<2: raise ValueError('Programación Mi.tv insuficiente')
    return filas

def actualizar_mitv_canal(canales, desde, hasta, cid, slug):
    canales.setdefault(cid, [])
    fecha=datetime.fromtimestamp(desde,GEN_TZ).date()-timedelta(days=1)
    ultima=datetime.fromtimestamp(hasta,GEN_TZ).date()
    oficial={}
    while fecha<=ultima:
        try:
            url=f'{MITV_URL}/{slug}/{fecha.isoformat()}/-180'
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':f'https://mi.tv/py/canales/{slug}','X-Requested-With':'XMLHttpRequest'})
            with urllib.request.urlopen(req,timeout=25) as r: html=r.read().decode('utf-8')
            filas=trece_inicios(html,fecha)
            for (a,t,d),(b,_,__) in zip(filas,filas[1:]):
                if a<b and b>desde and a<hasta: oficial[a]=[a,b,t,d]
        except Exception as exc: print(f'{cid} {fecha}: {exc}')
        fecha+=timedelta(days=1)
    programas=[]
    for p in sorted(oficial.values()):
        if programas and p[0]<programas[-1][1]: programas[-1][1]=p[0]
        programas.append(p)
    respaldo=[p for p in canales[cid] if not any(p[0]<q[1] and p[1]>q[0] for q in programas)]
    canales[cid]=programas+respaldo
    print(f'{cid} Mi.tv: {len(programas)} programas')


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
            # Ajustar antes de filtrar por la ventana de programación.
            if cid in CANALES_PARAGUAY:
                ini += DESFASE_PARAGUAY
                fin += DESFASE_PARAGUAY
            titulo = (el.findtext("title") or "").strip()
            detalle = (el.findtext("category") or "").strip()[:80]
            if (fin > desde and ini < hasta and titulo
                    and titulo.lower() not in RELLENO):
                canales[cid].append([ini, fin, titulo, detalle])
        el.clear()  # libera memoria: el XML puede pesar varios MB

    actualizar_gen(canales, desde, hasta)
    for cid, slug in CANALES_MITV.items():
        actualizar_mitv_canal(canales, desde, hasta, cid, slug)

    for lista in canales.values():
        lista.sort(key=lambda p: p[0])

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"generado": ahora, "canales": canales}, f,
                  ensure_ascii=False, separators=(",", ":"))

    con_datos = sum(1 for l in canales.values() if l)
    print(f"Listo: {con_datos}/{len(ids)} canales con programación -> {OUT_FILE}")
    for cid, lista in sorted(canales.items()):
        print(f"  {cid}: {len(lista)} programas")


if __name__ == "__main__":
    main()
