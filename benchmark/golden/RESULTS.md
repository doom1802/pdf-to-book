# Golden set: risultati ricalcolati

Report dell'esecuzione locale, riproducibile con `python benchmark/golden/run_benchmark.py` quando sono disponibili i PDF, le annotazioni e gli output dei parser usati nel test.

Nove pagine, normalizzazione CommonMark. Medie macro sulle sole pagine applicabili.

| Metrica | MinerU flash | Docling standard | Pagine applicabili (M/D) |
| --- | ---: | ---: | ---: |
| text_recovery | 99.80% | 99.04% | 9/9 |
| text_accuracy | 99.20% | 98.36% | 9/9 |
| block_precision | 64.06% | 97.87% | 9/9 |
| block_recall | 89.10% | 96.76% | 9/9 |
| block_f1 | 72.33% | 97.17% | 9/9 |
| block_type_accuracy | 73.30% | 91.66% | 9/9 |
| heading_level_accuracy | 81.25% | 68.75% | 8/8 |
| reading_order_accuracy | 100.00% | 100.00% | 9/9 |
| code_accuracy | 0.00% | 82.56% | 6/6 |
| code_text_recovery | 98.72% | 99.43% | 6/6 |
| code_type_accuracy | 0.00% | 88.33% | 6/6 |
| artifact_suppression_accuracy | 11.11% | 100.00% | 9/9 |
| figure_presence_recall | 100.00% | 100.00% | 1/1 |
| figure_recall | n/a | n/a | 0/0 |
| figure_verification_coverage | 0.00% | 0.00% | 1/1 |
| caption_recall | 50.00% | 0.00% | 2/2 |

## Accuratezza del testo per pagina

| Pagina | MinerU flash | Docling standard |
| --- | ---: | ---: |
| clean-code-page-035 | 98.60% | 97.22% |
| clean-code-page-050 | 99.96% | 98.73% |
| clean-code-page-100 | 99.11% | 99.78% |
| ddia-page-025 | 99.20% | 98.86% |
| ddia-page-035 | 99.02% | 99.38% |
| ddia-page-075 | 99.05% | 93.49% |
| linguaggio-c-page-007 | 99.94% | 99.48% |
| linguaggio-c-page-010 | 99.53% | 99.72% |
| linguaggio-c-page-050 | 98.39% | 98.60% |

## Interpretazione e limiti

- `figure_presence_recall` misura soltanto la presenza di blocchi figura; non prova la correttezza delle immagini.
- `figure_recall` confronta hash SHA-256 con riferimenti verificati nel golden set. Senza riferimenti restituisce `null`; la copertura esplicita quanti riferimenti sono verificabili. Un hash diverso non misura la similarità visiva tra ricampionamenti.
- Il golden set attuale non contiene hash di immagini verificati: la fedeltà visiva resta non misurata.
- Gli artefatti sono cercati anche dentro i paragrafi, sottraendo le occorrenze legittime nel testo golden. Un caso ambiguo richiede comunque revisione visiva.
- La fedeltà del codice conserva spazi iniziali, maiuscole e tag letterali. Le didascalie devono essere classificate come tali.
- Il matching rimane uno-a-uno con soglia 55%; fusioni e divisioni possono abbassare F1 pur conservando testo. Leggere insieme recupero e struttura.
- Le nove pagine non misurano tutta la varietà dei PDF. Non sono una classifica definitiva dei parser.
- Il confronto Markdown rimane distinto dalla conversione EPUB, che usa il JSON nativo di Docling.
