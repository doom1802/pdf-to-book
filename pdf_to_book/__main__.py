"""Convert a local PDF page range to a self-contained EPUB."""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .cover import add_pdf_cover
from .docling_adapter import adapt
from .epub import CSS, render_content, render_nav, write_epub
from .quality import quality_report
from .validate import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--pages',required=True,help='Inclusive PDF page range, e.g. 48-61')
    parser.add_argument('--title',required=True)
    parser.add_argument('--author',default='')
    parser.add_argument('--language',default='en')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--docling-json',type=Path,help='Reuse an existing native Docling export')
    parser.add_argument('--cover-page',type=int,default=1,help='PDF page to use as the cover (default: 1)')
    parser.add_argument('--no-cover',action='store_true',help='Do not add a cover image')
    parser.add_argument('--device',default='auto',choices=['auto','cpu','mps','cuda'])
    parser.add_argument('--enrich-formulas',action='store_true',
                        help='Recognize PDF formulas with the Docling formula model')
    parser.add_argument('--epubcheck',type=Path,help='Optional path to the official EPUBCheck JAR')
    parser.add_argument('--java',default='java',help='Java executable used by EPUBCheck')
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'[1-9]\d*-[1-9]\d*',args.pages): parser.error('--pages must be start-end')
    start,end=map(int,args.pages.split('-'))
    if start>end: parser.error('Page range is reversed')
    if not args.source.is_file(): parser.error('Source PDF not found')
    if args.output.suffix.lower()!='.epub':parser.error('--output must end in .epub')
    if args.cover_page < 1:parser.error('--cover-page must be positive')
    if args.epubcheck and not args.epubcheck.is_file():parser.error('EPUBCheck JAR not found')
    docling_command = None
    if args.docling_json is None:
        bundled_command = Path(sys.executable).parent / 'docling'
        docling_command = str(bundled_command) if bundled_command.is_file() else shutil.which('docling')
        if docling_command is None:
            parser.error('Docling is required to extract a PDF; install pdf-to-book[convert] or pass --docling-json')
    work=args.output.with_suffix('')
    work.mkdir(parents=True,exist_ok=True)
    native=args.docling_json
    if native is None:
        raw_dir=work/'docling'
        env=os.environ.copy()
        cache=Path(__file__).resolve().parents[1]/'benchmark/cache/huggingface'
        if cache.is_dir():env.setdefault('HF_HOME',str(cache))
        subprocess.run([docling_command,'convert',str(args.source),
            '--pipeline','standard','--no-ocr','--device',args.device,'--table-mode','fast',
            '--page-range',args.pages,'--to','json','--image-export-mode','referenced',
            *(['--enrich-formula'] if args.enrich_formulas else []),
            '--output',str(raw_dir)],check=True,env=env)
        native=raw_dir/(args.source.stem+'.json')
    exported=json.loads(native.read_text())
    if sorted(map(int,exported['pages']))!=list(range(start,end+1)):
        raise ValueError('Docling JSON does not contain exactly the requested PDF pages')
    origin=exported.get('origin',{}).get('filename')
    if origin and origin!=args.source.name:raise ValueError('Docling JSON source filename does not match the PDF')
    book=adapt(native,args.source,args.title,args.author,args.language,work/'assets')
    if not args.no_cover:
        add_pdf_cover(book,args.source,work/'assets',page_number=args.cover_page)
    book['source_sha256']=__import__('hashlib').sha256(args.source.read_bytes()).hexdigest()
    (work/'book.json').write_text(json.dumps(book,ensure_ascii=False,indent=2)+'\n')
    source_date_epoch = os.environ.get('SOURCE_DATE_EPOCH')
    modified = (
        datetime.fromtimestamp(int(source_date_epoch), timezone.utc)
        if source_date_epoch is not None else None
    )
    write_epub(book,work,args.output,modified=modified)
    result=validate(args.output)
    result.update(pages=book['pages'],blocks=len(book['blocks']),images=len(book['assets']),
                  code_blocks=sum(b['type']=='code' for b in book['blocks']),footnotes=len(book['footnotes']),
                  linked_footnotes=sum(bool(n.get('backlink')) for n in book['footnotes']),
                  joined_paragraphs=sum(bool(b.get('joined_ids')) for b in book['blocks']),warnings=book['warnings'])
    result['quality'] = quality_report(
        book,
        stylesheet=CSS,
        content_xhtml=render_content(book),
        navigation_xhtml=render_nav(book),
    )
    if args.epubcheck:
        checked=subprocess.run([args.java,'-jar',str(args.epubcheck),str(args.output),'--json',str(work/'epubcheck.json')],
                               capture_output=True,text=True)
        result['epubcheck']={'valid':checked.returncode==0,'exit_code':checked.returncode,
                             'output':checked.stdout+checked.stderr,'report':'epubcheck.json'}
        result['valid']=result['valid'] and checked.returncode==0
    (work/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'epub':str(args.output),'preview':str(work/'preview.html'),**result},ensure_ascii=False,indent=2))
    if not result['valid']:raise SystemExit(1)

if __name__=='__main__':main()
