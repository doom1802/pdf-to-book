# Parser benchmark

Questo benchmark confronta parser PDF sugli stessi libri e sulle stesse pagine.
È il registro di esperimenti locali: i PDF, gli output dei parser e le annotazioni derivate non sono inclusi nella repository. I comandi qui sotto richiedono quei file e ambienti opzionali per i parser citati.

La valutazione quantitativa basata su annotazioni manuali è descritta in [`golden/README.md`](golden/README.md). I primi risultati sperimentali sono in [`golden/RESULTS.md`](golden/RESULTS.md).

## Baseline

La prima prova usa MinerU 4.0 con il text layer del PDF, senza OCR forzato. Il confronto include i tier `flash`, `basic`, `standard` e `advanced`.

Pagine iniziali del test: `1-20` per ogni documento nella cartella `samples/`.

I risultati generati localmente vengono salvati in `benchmark/results/` e non sono versionati.

I risultati sintetici della prima esecuzione sono documentati in [`RESULTS.md`](RESULTS.md).

## Comandi MinerU

Baseline veloce:

```bash
.venv/bin/mineru-kit parse samples/clean-code-robert-c-martin.pdf \
  -o benchmark/results/mineru-flash/clean-code.md \
  --pages 1-20 \
  --tier flash \
  --ocr-mode txt
```

Parsing con modelli:

```bash
.venv/bin/mineru-kit parse samples/clean-code-robert-c-martin.pdf \
  -o benchmark/results/mineru-standard/clean-code.md \
  --pages 1-20 \
  --tier standard \
  --ocr-mode auto
```

Gli altri tier si eseguono sostituendo `standard` con `basic` o `advanced`.

## PaddleOCR-VL 1.6

Il runner crea una copia temporanea delle prime pagine senza modificare il PDF originale:

```bash
PADDLE_PDX_CACHE_HOME=benchmark/cache/paddlex \
  .venv-paddle/bin/python benchmark/run_paddleocr_vl.py \
  samples/clean-code-robert-c-martin.pdf \
  benchmark/results/paddleocr-vl-1.6/clean-code \
  --pages 3
```

## Docling

Pipeline veloce che usa direttamente la struttura del PDF:

```bash
HF_HOME=benchmark/cache/huggingface \
  .venv-docling/bin/docling convert \
  samples/clean-code-robert-c-martin.pdf \
  --pipeline native --page-range 1-20 --to md --to json \
  --image-export-mode referenced \
  --output benchmark/results/docling-native/clean-code
```

Pipeline con riconoscimento del layout e accelerazione Apple Silicon:

```bash
HF_HOME=benchmark/cache/huggingface \
  .venv-docling/bin/docling convert \
  samples/clean-code-robert-c-martin.pdf \
  --pipeline standard --no-ocr --device mps --table-mode fast \
  --page-range 1-20 --to md --to json \
  --image-export-mode referenced \
  --output benchmark/results/docling-standard/clean-code
```

## Criteri da misurare

- tempo di elaborazione;
- memoria utilizzata;
- completezza del testo;
- ordine di lettura;
- riconoscimento di titoli e capitoli;
- conservazione di codice, immagini, tabelle e formule;
- facilità di trasformazione in EPUB.

## Profilazione dettagliata del percorso scelto

Dopo la scelta di Docling, il costo del percorso completo viene scomposto con:

```bash
.venv-docling/bin/python benchmark/profile_docling.py \
  --source samples/clean-code-robert-c-martin.pdf \
  --pages 48-61 --device cpu \
  --quality-baseline tests/fixtures/meaningful-names-quality.json \
  --output benchmark/profiles/current-cpu-b4.json
```

Il profiler accetta più volte `--source`, quindi misura direttamente l'input
come array di path e riutilizza la stessa pipeline. Il rapporto completo è in
[`../docs/memory-profile.md`](../docs/memory-profile.md).
