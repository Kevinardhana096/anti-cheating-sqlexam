"""Check portable local links, anchors and script references in product documentation."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]


def slug(value):
    value=re.sub(r'<[^>]*>','',value).lower()
    return re.sub(r'[^\w\- ]','',value).replace(' ','-')


def main():
    files=[ROOT/'README.md',ROOT/'INSTALLATION MANUAL.md']+sorted((ROOT/'docs').rglob('*.md'))
    files=[p for p in files if p.name!='antislop.md']
    errors=[];links=0;scripts=set()
    for path in files:
        text=path.read_text(encoding='utf-8')
        prose=re.sub(r'```.*?```','',text,flags=re.S)
        for match in re.finditer(r'!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)',prose):
            target=match[1].strip('<>');parsed=urlsplit(target)
            if parsed.scheme or parsed.netloc:
                if parsed.scheme=='file':errors.append(f'{path.relative_to(ROOT)}: nonportable {target}')
                continue
            links+=1
            destination=(path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            if not destination.exists():
                errors.append(f'{path.relative_to(ROOT)}: missing {target}');continue
            if parsed.fragment and destination.suffix=='.md':
                headings=[];counts={}
                content=re.sub(r'```.*?```','',destination.read_text(encoding='utf-8'),flags=re.S)
                for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$',content,re.M):
                    base=slug(heading);n=counts.get(base,0);counts[base]=n+1
                    headings.append(base+(f'-{n}' if n else ''))
                if unquote(parsed.fragment) not in headings:
                    errors.append(f'{path.relative_to(ROOT)}: missing anchor {target}')
        for script in re.findall(r'scripts/[A-Za-z0-9_-]+\.(?:py|cjs)',text):
            scripts.add(script)
            if not (ROOT/script).is_file():errors.append(f'{path.relative_to(ROOT)}: missing script {script}')
    print(f'{len(files)} product Markdown files; {links} local links; {len(scripts)} distinct script references.')
    for error in errors:print(error)
    print(f'{len(errors)} errors. External URLs, vendor notices and agent rules are not network-validated.')
    return int(bool(errors))


if __name__=='__main__':
    sys.exit(main())
