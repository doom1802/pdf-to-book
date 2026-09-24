"""Local EPUB structural checks; these supplement, not replace, EPUBCheck."""
import posixpath
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_STORED

NS = {'opf':'http://www.idpf.org/2007/opf','dc':'http://purl.org/dc/elements/1.1/',
      'c':'urn:oasis:names:tc:opendocument:xmlns:container','h':'http://www.w3.org/1999/xhtml'}

def validate(path):
    errors, checks = [], []
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names)!=len(set(names)): errors.append('Duplicate ZIP entries')
        if archive.testzip(): errors.append('Corrupt ZIP entry')
        first=archive.infolist()[0]
        if first.filename!='mimetype' or first.compress_type!=ZIP_STORED or archive.read(first)!=b'application/epub+zip':
            errors.append('Invalid mimetype entry')
        checks.append('ZIP integrity and uncompressed first mimetype')
        root=ET.fromstring(archive.read('META-INF/container.xml'))
        package_path=root.find('c:rootfiles/c:rootfile',NS).attrib['full-path']
        package=ET.fromstring(archive.read(package_path)); base=posixpath.dirname(package_path)
        for tag in ['title','language','identifier']:
            if not package.findtext('opf:metadata/dc:'+tag,namespaces=NS): errors.append('Missing '+tag)
        if package.get('version')!='3.0': errors.append('Invalid package version')
        identifier=package.get('unique-identifier')
        if not any(e.get('id')==identifier for e in package.findall('opf:metadata/dc:identifier',NS)): errors.append('Identifier does not resolve')
        if package.find("opf:metadata/opf:meta[@property='dcterms:modified']",NS) is None: errors.append('Missing modified date')
        items=package.findall('opf:manifest/opf:item',NS)
        if sum('nav' in i.get('properties','').split() for i in items)!=1: errors.append('Exactly one nav required')
        ids={i.get('id') for i in items}
        if len(ids)!=len(items): errors.append('Duplicate manifest IDs')
        spine=package.findall('opf:spine/opf:itemref',NS)
        if not spine: errors.append('Empty spine')
        for item in spine:
            if item.get('idref') not in ids: errors.append('Unresolved spine item')
        resources={posixpath.normpath(posixpath.join(base,i.get('href'))):i for i in items}
        for resource in resources:
            if resource not in names: errors.append('Missing manifest resource: '+resource)
        checks.append('Metadata, manifest resources, navigation declaration and spine')
        documents={}
        id_sets={}
        for name in resources:
            if name.endswith('.xhtml') and name in names:
                document=ET.fromstring(archive.read(name));documents[name]=document
                if document.tag!='{'+NS['h']+'}html': errors.append('Not XHTML: '+name)
                if any(e.tag=='{http://www.w3.org/1998/Math/MathML}math' for e in document.iter()):
                    if 'mathml' not in resources[name].get('properties','').split():
                        errors.append('MathML property missing: '+name)
                values=[e.get('id') for e in document.iter() if e.get('id')]
                if len(values)!=len(set(values)): errors.append('Duplicate XHTML IDs: '+name)
                id_sets[name]=set(values)
        links=0
        for name,document in documents.items():
            for element in document.iter():
                for attribute in ['href','src']:
                    target=element.get(attribute)
                    if target is None: continue
                    url=urlparse(target)
                    if url.scheme in {'http','https','mailto'}:continue
                    if url.scheme or url.netloc:
                        errors.append('Unsupported resource URI: '+target);continue
                    resource=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(url.path))) if url.path else name
                    if resource not in resources: errors.append('Undeclared link or asset: '+resource)
                    if url.fragment and unquote(url.fragment) not in id_sets.get(resource,set()):errors.append('Broken anchor: '+target)
                    links+=1
                if element.tag=='{'+NS['h']+'}img' and 'alt' not in element.attrib:errors.append('Image missing alt text')
        checks.append(f'Well-formed XHTML, unique IDs, image alternatives and {links} local links')
    return {'valid':not errors,'checks':checks,'errors':errors,'scope':'Local structural validation; not full EPUBCheck conformance.'}

if __name__=='__main__':
    import json,sys
    result=validate(Path(sys.argv[1]));print(json.dumps(result,indent=2));sys.exit(0 if result['valid'] else 1)
