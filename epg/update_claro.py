#!/usr/bin/env python3
"""Fusiona 10 canales Claro con epg/epg.json sin alterar otros canales.
Admite archivo local como argumento o CLARO_EPG_SOURCE_URL (secreto GitHub).
No guarda credenciales ni la respuesta original en el repositorio.
"""
import json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'epg.json'
CHANNELS={
 '4839':'GEN.py','488':'Trece.py','481':'Paravision.py',
 '2637':'SurTV.py','3436':'Venus Media.py','3294':'Venus.py',
 '6142':'Ñanduti.py','6634':'America Paraguay.py',
 '9299':'Popu TV.py','2588':'HEI.py'
}

def load_source():
 if len(sys.argv)>1:
  return json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
 url=os.getenv('CLARO_EPG_SOURCE_URL','').strip()
 if not url: raise RuntimeError('CLARO_EPG_SOURCE_URL no configurada; se conserva EPG actual')
 # Actualizar intervalo en URL para evitar reutilizar fechas pasadas.
 from datetime import datetime,timedelta,timezone
 now=datetime.now(timezone(timedelta(hours=-3)))
 qs=urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query,keep_blank_values=True)
 dates={'date_from':now.strftime('%Y%m%d%H%M%S'),'date_to':(now+timedelta(hours=36)).strftime('%Y%m%d%H%M%S')}
 qs=[(k,dates.get(k,v)) for k,v in qs]
 parts=urllib.parse.urlsplit(url)
 url=urllib.parse.urlunsplit((parts.scheme,parts.netloc,parts.path,urllib.parse.urlencode(qs),parts.fragment))
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=45) as resp:
  return json.load(resp)

def main():
 source=load_source()
 channels=source.get('response',{}).get('channels')
 if not isinstance(channels,list):raise ValueError('La respuesta no contiene response.channels')
 original=json.loads(OUT.read_text(encoding='utf-8'))
 if not isinstance(original.get('canales'),dict):raise ValueError('epg.json no válido')
 now=int(time.time()); changed=0
 for ch in channels:
  target=CHANNELS.get(str(ch.get('id')))
  if not target:continue
  programs=[]
  for e in ch.get('events',[]):
   try:
    a=int(e['unix_begin']);b=int(e['unix_end']);name=str(e['name']).strip()
   except (KeyError,ValueError,TypeError):continue
   if a>=b or not name:continue
   # En modo automático, no sobrescribir con datos caducados.
   if len(sys.argv)==1 and (b<now-3*3600 or a>now+48*3600):continue
   programs.append([a,b,name,str(e.get('description') or '')])
  programs.sort(key=lambda p:p[0])
  if programs:
   original['canales'][target]=programs
   changed+=1
 if not changed:raise RuntimeError('No hay programas nuevos válidos; se conserva el archivo anterior')
 original['generado']=now
 temp=OUT.with_suffix('.json.tmp')
 temp.write_text(json.dumps(original,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 temp.replace(OUT)
 print(f'Actualizados {changed}/10 canales Claro; los demás se conservaron')

if __name__=='__main__':main()
