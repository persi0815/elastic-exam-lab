"""Parser for the supported Kibana Console text syntax (not a JS evaluator)."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, unquote

class ConsoleError(ValueError):
    pass

@dataclass
class Request:
    method: str
    path: str
    body: object | None
    raw_body: str | None
    content_type: str
    line: int

    def public(self):
        return {'method':self.method,'path':self.path,'body':self.body,'line':self.line}

def _unique(pairs):
    d={}
    for key,val in pairs:
        if key in d:
            raise ConsoleError(f'중복 JSON 키 "{key}". 같은 객체에 같은 키를 두 번 넣을 수 없습니다. processors/조건은 배열의 별도 객체로 분리하세요.')
        d[key]=val
    return d

def strict_loads(value):
    return json.loads(value,object_pairs_hook=_unique,parse_constant=lambda x: (_ for _ in ()).throw(ConsoleError(f'JSON 상수 {x}는 지원되지 않습니다.')))

def sanitize(text: str) -> str:
    """Strip //, #, /* */ outside strings; encode Console triple-quoted strings."""
    result=[];i=0;n=len(text)
    while i<n:
        if text.startswith('"""',i):
            end=text.find('"""',i+3)
            if end<0: raise ConsoleError('닫히지 않은 삼중 따옴표 문자열입니다.')
            value=text[i+3:end]
            result.append(json.dumps(value,ensure_ascii=False))
            result.append('\n'*value.count('\n'))
            i=end+3
        elif text[i]=='"':
            start=i;i+=1
            while i<n:
                if text[i]=='\\': i+=2;continue
                if text[i]=='"': i+=1;break
                i+=1
            else: raise ConsoleError('닫히지 않은 JSON 문자열입니다.')
            result.append(text[start:i])
        elif text.startswith('//',i) or text[i]=='#':
            end=text.find('\n',i)
            if end<0: break
            result.append(' '*(end-i));i=end
        elif text.startswith('/*',i):
            end=text.find('*/',i+2)
            if end<0: raise ConsoleError('닫히지 않은 /* */ 주석입니다.')
            result.append(''.join('\n' if ch=='\n' else ' ' for ch in text[i:end+2]));i=end+2
        else:
            result.append(text[i]);i+=1
    return ''.join(result)

HEADER=re.compile(r'^\s*(GET|POST|PUT|DELETE|HEAD|PATCH)\s+([^\s]+)[ \t]*$',re.M)

def parse_console(text: str) -> list[Request]:
    if not isinstance(text,str): raise ConsoleError('코드는 문자열이어야 합니다.')
    if len(text)>2_000_000: raise ConsoleError('요청 스크립트는 2 MB 이하로 입력하세요.')
    clean=sanitize(text).strip()
    if not clean: raise ConsoleError('GET index/_search처럼 HTTP 메서드와 경로를 입력하세요.')
    headers=list(HEADER.finditer(clean))
    if not headers or clean[:headers[0].start()].strip():
        raise ConsoleError('요청은 GET /path, PUT /path 같은 줄로 시작해야 합니다. curl/셸 명령은 지원하지 않습니다.')
    if len(headers)>100: raise ConsoleError('한 번에 최대 100개 요청을 실행할 수 있습니다.')
    requests=[]
    for j,h in enumerate(headers):
        method,path=h.group(1),h.group(2)
        if re.match(r'^(https?|ftp|file):',path,re.I) or '://' in path or path.startswith('//') or '\\' in path:
            raise ConsoleError('클러스터 내부 상대 API 경로만 허용합니다. 외부 URL은 실행할 수 없습니다.')
        # A CCS target such as cluster2:blogs is an index target, not a URL scheme.
        if not path.startswith('/'):path='/'+path
        parts=urlsplit(path)
        if '..' in unquote(parts.path).split('/'):
            raise ConsoleError('상위 디렉터리 경로는 허용하지 않습니다.')
        raw=clean[h.end():headers[j+1].start() if j+1<len(headers) else len(clean)].strip()
        body=None;ctype='application/json';encoded=None
        try:
            if raw:
                endpoint=parts.path.rstrip('/').split('/')[-1]
                if endpoint in ('_bulk','_msearch','_msearch/template') or parts.path.endswith('/_msearch/template'):
                    lines=[line for line in raw.splitlines() if line.strip()]
                    body=[strict_loads(line) for line in lines]
                    encoded='\n'.join(json.dumps(x,ensure_ascii=False,separators=(',',':')) for x in body)+'\n'
                    ctype='application/x-ndjson'
                else:
                    body=strict_loads(raw)
                    if not isinstance(body,(dict,list)):
                        raise ConsoleError('요청 본문은 JSON 객체 또는 배열이어야 합니다.')
                    encoded=json.dumps(body,ensure_ascii=False,separators=(',',':'))
        except json.JSONDecodeError as e:
            line=clean[:h.end()].count('\n')+1+e.lineno
            raise ConsoleError(f'{method} {path}: JSON 오류 (대략 {line}행): {e.msg}. 쉼표/중괄호와 processors 배열을 확인하세요.') from e
        requests.append(Request(method,path,body,encoded,ctype,clean[:h.start()].count('\n')+1))
    return requests
