# Prestazioni e quality gate

Prima di ottimizzare è stata fissata una firma semantica del capitolo campione. La firma copre contenuto e ordine dei blocchi, gerarchia dei titoli, struttura dei capitoli ricavata dall'indice PDF, codice e indentazione, note, collegamenti, copertina, immagini, dimensioni relative e CSS. Percorsi locali, coordinate PDF, versione del parser e misure temporali non fanno parte della firma perché non cambiano ciò che riceve il lettore.

Questa è una baseline storica su campioni locali. Il PDF, l'export Docling e il contratto derivato non sono distribuiti; i comandi del benchmark richiedono di fornirli separatamente.

Il contratto corrente è in `tests/fixtures/meaningful-names-quality.json`. Una modifica intenzionale al risultato richiede revisione dell'EPUB e aggiornamento esplicito del contratto. Non aggiornare la firma soltanto per far passare un test.

## Baseline del 21 settembre 2026

Ambiente: macOS 26.5 arm64, Python 3.12.13, CPU, modelli locali già scaricati.

| Fase | Ripetizioni | Tempo mediano | Intervallo | Picco RSS mediano |
| --- | ---: | ---: | ---: | ---: |
| JSON Docling → EPUB | 7 | 0,542 s | 0,527–0,606 s | 73,52 MB |
| PDF → Docling → EPUB | 3 | 9,697 s | 8,865–33,934 s | 2.892,48 MB |

Il massimo di 33,934 secondi rappresenta il primo avvio freddo osservato. La fase EPUB include ora il rendering deterministico della prima pagina come copertina. Il picco della pipeline completa rimane dominato dai modelli; le ottimizzazioni iniziali dovrebbero concentrarsi su inizializzazione, batch e ciclo di vita del processo Docling.

I dati grezzi sono in `benchmark/performance-baseline-epub.json` e `benchmark/performance-baseline-full.json`. Sono riferimenti per questa macchina, non soglie universali per CI.

## Comandi

Quality gate funzionale:

```bash
.venv-docling/bin/python -m unittest discover -s tests -v
.venv-docling/bin/python -m unittest discover -s benchmark/golden -p 'test_*.py' -v
```

Benchmark della sola fase EPUB:

```bash
.venv-docling/bin/python benchmark/benchmark_pipeline.py \
  --stage epub --runs 7 \
  --source samples/clean-code-robert-c-martin.pdf \
  --docling-json output/chapter/docling/clean-code-robert-c-martin.json \
  --pages 48-61 --title 'Clean Code — Meaningful Names' \
  --author 'Robert C. Martin; chapter by Tim Ottinger' --language en \
  --quality-baseline tests/fixtures/meaningful-names-quality.json
```

Per includere parsing e modelli, sostituire `--stage epub` con `--stage full --device cpu`.

Per confrontare automaticamente una modifica con la baseline della stessa macchina:

```bash
# aggiungere al comando precedente
--performance-baseline benchmark/performance-baseline-epub.json \
--max-time-regression 0.10 --max-memory-regression 0.10
```

Il benchmark esegue ogni ripetizione in un processo nuovo, controlla la firma di qualità a ogni giro e misura il picco RSS. Il confronto prestazionale fallisce se mediana di tempo o memoria supera la tolleranza scelta. La quality gate usa confronto esatto e non ha tolleranza.

Per l'attribuzione a import, caricamento dei singoli modelli, inferenza, code e
array di documenti vedere [`memory-profile.md`](memory-profile.md). Quel profilo
usa campionamento RSS ogni 10 ms e conserva le tracce grezze in
`benchmark/profiles/`.

## Riproducibilità

Impostando `SOURCE_DATE_EPOCH`, due conversioni semanticamente identiche producono lo stesso EPUB byte per byte. Il test automatico copre ordine e timestamp delle voci ZIP, identificatore della pubblicazione e contenuti.

```bash
SOURCE_DATE_EPOCH=1767225600 .venv-docling/bin/python -m pdf_to_book ...
```

Senza questa variabile, `dcterms:modified` riflette l'ora reale della conversione, come previsto per l'uso normale.
