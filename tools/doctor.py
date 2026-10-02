#!/usr/bin/env python3
"""Read-only local diagnostics. Uses real ES/Kibana when the lab is running."""
from __future__ import annotations
import argparse,base64,json,os,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url');a=p.parse_args()
    env={}
    if (ROOT/'.env').exists():
        for line in (ROOT/'.env').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):k,v=line.split('=',1);env[k.strip()]=v.strip()
    port=os.getenv('LAB_PORT',env.get('LAB_PORT','8787'));url=(a.url or 'http://127.0.0.1:'+port).rstrip('/')
    # The container's own HTTP port is fixed, regardless of the host port mapping.
    if os.getenv('LAB_STATE_DIR')=='/opt/lab/state' and not a.url:url='http://127.0.0.1:8787'
    pw=os.getenv('ELASTIC_PASSWORD',env.get('ELASTIC_PASSWORD','ExamLab2026'))
    headers={'Authorization':'Basic '+base64.b64encode(('elastic:'+pw).encode()).decode()}
    failures=[]
    def get(path):
        try:
            with urlopen(Request(url+path,headers=headers),timeout=20) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,e.read().decode()
    try:
        code,st=get('/api/status');print('LAB HTTP',code);print(json.dumps(st,ensure_ascii=False,indent=2))
        if code!=200 or st['lab']['phase']!='ready':failures.append('실습 데이터 준비 상태')
        for n in (1,2):
            c='cluster'+str(n);code,data=get(f'/kibana{n}/api/status')
            print(f'KIBANA {n}: HTTP {code}')
            if code!=200:failures.append(f'Kibana {n} 연결/인증')
            else:
                version=data.get('version',{}).get('number');print('  version:',version)
                if version and version!=st['engine_version']:failures.append(f'Kibana {n} 버전 불일치')
        print('\n실제 editor URL:',url+'/kibana1/app/dev_tools#/console')
        print('실제 editor URL:',url+'/kibana2/app/dev_tools#/console')
        if failures:print('FAIL:',', '.join(failures));return 1
        print('PASS: 실습 준비 및 두 실제 Kibana의 상태 API 확인. 브라우저 입력/검색 의미까지 검증한 것은 아닙니다.');return 0
    except Exception as e:
        print('FAIL:',e);print('docker compose ps\ndocker compose logs --tail=100 kibana1 kibana2 app');return 1
if __name__=='__main__':sys.exit(main())
