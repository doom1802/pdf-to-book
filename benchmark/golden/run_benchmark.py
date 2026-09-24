#!/usr/bin/env python3
"""Rebuild all normalized predictions and the reproducible golden-set report."""
import json
from pathlib import Path
from statistics import mean
from evaluate import evaluate, load_page
from markdown_to_prediction import convert
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'benchmark/results/golden-v0'
GOLD = ROOT / 'benchmark/golden'

def markdown_path(page, parser):
    book, number = page['id'].rsplit('-page-', 1)
    if parser == 'mineru-flash':
        return BASE / parser / book / f'page-{number}.md'
    first = {'clean-code': '035', 'ddia': '025', 'linguaggio-c': '007'}
    folder = book if number == first[book] else f'{book}-p{number}'
    return BASE / parser / folder / (Path(page['source']).stem + '.md')

def main():
    results = {}
    for parser in ['mineru-flash', 'docling-standard']:
        rows = []
        for entry in json.loads((GOLD / 'manifest.json').read_text())['pages']:
            gold = load_page(GOLD / 'annotations' / (entry['id'] + '.json'))
            source = markdown_path(entry, parser)
            prediction = convert(gold, source.read_text(), parser, base_dir=source.parent)
            dest = BASE / 'predictions' / parser / (entry['id'] + '.json')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(prediction, ensure_ascii=False, indent=2)+'\n')
            rows.append(evaluate(gold, prediction))
        keys = rows[0]['metrics_percent']
        summary = {}
        for key in keys:
            values = [r['metrics_percent'][key] for r in rows if r['metrics_percent'][key] is not None]
            summary[key] = {'mean': round(mean(values), 2) if values else None, 'pages': len(values)}
        results[parser] = {'pages': rows, 'summary': summary}
    (BASE / 'evaluation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    def fmt(value): return 'n/a' if value is None else f'{value:.2f}%'
    lines = ['# Golden set: risultati ricalcolati', '',
             'Report riproducibile con `.venv-docling/bin/python benchmark/golden/run_benchmark.py`.', '',
             'Nove pagine, normalizzazione CommonMark. Medie macro sulle sole pagine applicabili.', '',
             '| Metrica | MinerU flash | Docling standard | Pagine applicabili (M/D) |',
             '| --- | ---: | ---: | ---: |']
    for key in results['mineru-flash']['summary']:
        a,b = [results[p]['summary'][key] for p in results]
        lines.append(f"| {key} | {fmt(a['mean'])} | {fmt(b['mean'])} | {a['pages']}/{b['pages']} |")
    lines += ['', '## Accuratezza del testo per pagina', '', '| Pagina | MinerU flash | Docling standard |', '| --- | ---: | ---: |']
    for a,b in zip(results['mineru-flash']['pages'], results['docling-standard']['pages']):
        lines.append(f"| {a['gold_id']} | {fmt(a['metrics_percent']['text_accuracy'])} | {fmt(b['metrics_percent']['text_accuracy'])} |")
    lines += ['', '## Interpretazione e limiti', '',
        '- `figure_presence_recall` misura soltanto la presenza di blocchi figura; non prova la correttezza delle immagini.',
        '- `figure_recall` confronta hash SHA-256 con riferimenti verificati nel golden set. Senza riferimenti restituisce `null`; la copertura esplicita quanti riferimenti sono verificabili. Un hash diverso non misura la similarità visiva tra ricampionamenti.',
        '- Il golden set attuale non contiene hash di immagini verificati: la fedeltà visiva resta non misurata.',
        '- Gli artefatti sono cercati anche dentro i paragrafi, sottraendo le occorrenze legittime nel testo golden. Un caso ambiguo richiede comunque revisione visiva.',
        '- La fedeltà del codice conserva spazi iniziali, maiuscole e tag letterali. Le didascalie devono essere classificate come tali.',
        '- Il matching rimane uno-a-uno con soglia 55%; fusioni e divisioni possono abbassare F1 pur conservando testo. Leggere insieme recupero e struttura.',
        '- Le nove pagine non misurano tutta la varietà dei PDF. Non sono una classifica definitiva dei parser.',
        '- Il confronto Markdown rimane distinto dalla conversione EPUB, che usa il JSON nativo di Docling.', '']
    (GOLD / 'RESULTS.md').write_text('\n'.join(lines))
    print('Rebuilt 18 predictions, evaluation.json and RESULTS.md')
if __name__ == '__main__': main()
