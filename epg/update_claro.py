#!/usr/bin/env python3
"""Actualiza solo diez canales paraguayos en epg/epg.json.

Acepta un archivo JSON local como argumento o CLARO_EPG_SOURCE_URL.
No registra URLs, identificadores de sesión ni respuestas completas.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'epg.json'
CHANNELS = {
    '4839': 'GEN.py', '488': 'Trece.py', '481': 'Paravision.py',
    '2637': 'SurTV.py', '3436': 'Venus Media.py', '3294': 'Venus.py',
    '6142': 'Ñanduti.py', '6634': 'America Paraguay.py',
    '9299': 'Popu TV.py', '2588': 'HEI.py',
}


def load_source():
    if len(sys.argv) > 1:
        return json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))

    url = os.environ.get('CLARO_EPG_SOURCE_URL', '').strip()
    if not url:
        raise RuntimeError('CLARO_EPG_SOURCE_URL no configurada')

    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != 'mfwkweb-api.clarovideo.net' or parts.path != '/services/epg/channel':
        raise ValueError('La fuente debe ser el endpoint HTTPS EPG de Claro Video')

    # Chrome solicitó 24 horas entre las 23:00 de dos días consecutivos.
    # Se conserva la hora de inicio original de la URL y se desplaza el día.
    params = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    original = dict(params)
    try:
        start_time = datetime.strptime(original['date_from'], '%Y%m%d%H%M%S').time()
    except (KeyError, ValueError):
        start_time = datetime.strptime('230000', '%H%M%S').time()

    local_now = datetime.now(timezone(timedelta(hours=-3)))
    start = local_now.replace(hour=start_time.hour, minute=start_time.minute,
                              second=start_time.second, microsecond=0)
    if start > local_now:
        start -= timedelta(days=1)
    end = start + timedelta(days=1)

    replacements = {'date_from': start.strftime('%Y%m%d%H%M%S'),
                    'date_to': end.strftime('%Y%m%d%H%M%S')}
    updated = [(key, replacements.get(key, value)) for key, value in params]
    for key, value in replacements.items():
        if key not in original:
            updated.append((key, value))
    request_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                           urllib.parse.urlencode(updated), ''))
    request = urllib.request.Request(request_url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    })
    print(f'Solicitando 24 horas de EPG desde {replacements["date_from"]} hasta {replacements["date_to"]} (hora Paraguay)')
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Claro devolvió HTTP {exc.code}; revisar sesión o parámetros') from None
    except urllib.error.URLError:
        raise RuntimeError('No fue posible conectar con la API EPG de Claro') from None


def main():
    source = load_source()
    if not isinstance(source, dict):
        raise ValueError('La respuesta de Claro no es un objeto JSON')
    response = source.get('response')
    if not isinstance(response, dict):
        # No mostrar msg completo, ya que podría contener datos de sesión.
        raise RuntimeError(f'Claro no devolvió datos EPG (status={str(source.get("status"))[:30]}); response es nulo o inválido')
    channels = response.get('channels')
    if not isinstance(channels, list) or not channels:
        raise RuntimeError('Claro no devolvió una lista de canales EPG')

    original = json.loads(OUT.read_text(encoding='utf-8'))
    if not isinstance(original, dict) or not isinstance(original.get('canales'), dict):
        raise ValueError('epg.json no válido')

    now = int(time.time())
    changed = 0
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        target = CHANNELS.get(str(ch.get('id')))
        if not target:
            continue
        events = ch.get('events')
        if not isinstance(events, list):
            continue
        programs = []
        for event in events:
            if not isinstance(event, dict):
                continue
            try:
                start = int(event['unix_begin'])
                end = int(event['unix_end'])
                title = str(event['name']).strip()
            except (KeyError, ValueError, TypeError):
                continue
            if start >= end or not title:
                continue
            if len(sys.argv) == 1 and (end < now - 3 * 3600 or start > now + 48 * 3600):
                continue
            programs.append([start, end, title, str(event.get('description') or '')])
        programs.sort(key=lambda p: p[0])
        if programs:
            original['canales'][target] = programs
            changed += 1

    if changed == 0:
        raise RuntimeError('Claro no entregó programas válidos para los 10 canales; no se modifica epg.json')

    original['generado'] = now
    temp = OUT.with_suffix('.json.tmp')
    temp.write_text(json.dumps(original, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(OUT)
    print(f'Actualizados {changed}/10 canales Claro; los demás se conservaron')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Claro no disponible: {exc}. Se conserva el EPG anterior.', file=sys.stderr)
        sys.exit(1)
