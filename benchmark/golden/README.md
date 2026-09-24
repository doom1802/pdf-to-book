# Golden set per il parsing PDF

Il golden set descrive manualmente ciò che un parser dovrebbe ricostruire da ogni pagina. Le annotazioni derivano dalla pagina renderizzata, non dall'output di MinerU, Docling o PaddleOCR.
Il codice del valutatore e lo schema sono pubblici; le annotazioni e le predizioni locali, derivate da documenti di terzi, non sono distribuite. I test unitari del valutatore usano casi sintetici.

## Obiettivo

Misurare separatamente gli aspetti che contano per un EPUB:

- completezza e correttezza del testo;
- riconoscimento dei tipi di blocco;
- gerarchia dei titoli;
- ordine di lettura;
- conservazione del codice e della sua indentazione;
- riconoscimento di liste, figure e didascalie;
- esclusione di intestazioni ricorrenti e numeri di pagina.

Un unico punteggio aggregato può essere aggiunto in seguito, ma non deve sostituire le metriche individuali.

## Struttura

- `manifest.json`: pagine selezionate, caratteristiche e stato dell'annotazione;
- `schema.json`: schema delle annotazioni e delle predizioni normalizzate;
- `annotations/`: verità di riferimento annotata manualmente;
- `evaluate.py`: confronto tra un'annotazione e una predizione nello stesso formato;
- `build_review_pdf.py`: genera un confronto visivo tra pagina originale e contenuto ricostruito dal parser.

Il dataset iniziale contiene 9 pagine revisionate manualmente, 3 per ciascun libro di esempio.

Le immagini renderizzate sono materiale temporaneo di revisione e non vengono incluse nel dataset.

## Regole di annotazione

1. Trascrivere il contenuto visibile correggendo soltanto gli artefatti tipografici del PDF, come parole spezzate a fine riga.
2. Conservare punteggiatura, maiuscole, simboli e indentazione significativa del codice.
3. Creare un blocco per ogni unità semantica, non per ogni riga tipografica.
4. Segnare con `include_in_epub: false` intestazioni ricorrenti e numeri di pagina.
5. Usare `reading_order` per l'ordine che il lettore deve seguire nell'EPUB.
6. Non usare l'output di un parser come fonte dell'annotazione.

## Metriche iniziali

`evaluate.py` restituisce percentuali indipendenti:

- `text_recovery`: quota del testo golden ritrovata in ordine nell'output, indipendentemente dal tipo di blocco e dal testo extra;
- `text_accuracy`: similarità carattere per carattere sul testo destinato all'EPUB;
- `block_precision`, `block_recall`, `block_f1`: presenza dei blocchi semantici;
- `block_type_accuracy`: correttezza del tipo dei blocchi abbinati;
- `heading_level_accuracy`: correttezza della gerarchia dei titoli;
- `reading_order_accuracy`: ordine relativo dei blocchi abbinati;
- `code_text_recovery`: quota del contenuto del codice ritrovata in qualsiasi blocco, anche se classificato come testo generico;
- `code_type_accuracy`: quota dei blocchi di codice riconosciuta semanticamente come `code`;
- `code_accuracy`: fedeltà dei blocchi classificati come codice, inclusi ritorni a capo e indentazione;
- `artifact_suppression_accuracy`: esclusione di header, footer e numeri di pagina;
- `figure_recall` e `caption_recall`: conservazione degli elementi non testuali.

Le predizioni dei parser dovranno essere convertite nello schema comune con adattatori specifici. In questo modo il valutatore rimane indipendente dal parser.
Le metriche non applicabili a una pagina sono restituite come `null`, non come un 100% artificiale.

Questa separazione evita di confondere tre casi diversi: testo mancante, testo presente nel blocco sbagliato e testo correttamente classificato ma con formattazione danneggiata.

## Esecuzione

```bash
python3 benchmark/golden/evaluate.py \
  benchmark/golden/annotations/clean-code-page-035.json \
  path/to/prediction.json
```

## Revisione visiva

Il PDF di revisione mostra, per ogni pagina e parser:

- la pagina originale a sinistra;
- la ricostruzione semantica a destra;
- il tipo assegnato a ogni blocco;
- le metriche principali della pagina nell'intestazione.

Non prova a riprodurre esattamente l'impaginazione originale: il reflow è intenzionale e rende più evidenti errori di classificazione, ordine, codice e contenuti mancanti.

```bash
python3 benchmark/golden/build_review_pdf.py \
  --gold-dir benchmark/golden/annotations \
  --prediction mineru-flash=benchmark/results/golden-v0/predictions/mineru-flash \
  --prediction docling-standard=benchmark/results/golden-v0/predictions/docling-standard \
  --output output/pdf/golden-set-visual-review.pdf
```

Le annotazioni con stato `draft` devono essere controllate nel PDF e promosse a `reviewed` soltanto dopo la revisione manuale.

## Revisore interattivo

Il revisore locale consente di correggere i blocchi, riordinarli, cambiarne il tipo, decidere se includerli nell'EPUB e confrontarli con le predizioni disponibili.

```bash
.venv-docling/bin/python benchmark/reviewer/server.py
```

Aprire <http://127.0.0.1:8765>. Il salvataggio aggiorna sia l'annotazione JSON sia lo stato della pagina nel manifest. I dettagli sono in [`../reviewer/README.md`](../reviewer/README.md).

## Correzioni e riproducibilità

La normalizzazione usa `markdown-it-py` (CommonMark), conserva i tag letterali nel codice inline e nei fenced block e non elimina l'indentazione iniziale. Riconosce anche fence con tilde, liste distinte e tabelle. Le figure conservano URI e, quando la risorsa locale è disponibile, SHA-256.

- `figure_presence_recall` misura soltanto quanti blocchi figura sono presenti;
- `figure_recall` richiede hash golden verificati ed è `null` quando mancano;
- `figure_verification_coverage` dichiara la copertura dei riferimenti verificabili;
- `caption_recall` richiede anche la classificazione `caption`;
- la soppressione degli artefatti controlla le occorrenze anche dentro paragrafi, tenendo conto di quelle già presenti legittimamente nel golden set.

Gli hash delle immagini non sono ancora annotati nel golden set attuale. La precedente percentuale del 100% sulle figure va interpretata soltanto come riconoscimento della presenza, non come conservazione verificata del contenuto.

```bash
.venv-docling/bin/python benchmark/golden/run_benchmark.py
```

Questo comando rigenera le predizioni, il report leggibile e `benchmark/results/golden-v0/evaluation.json`. Fallisce se mancano output sorgenti, invece di produrre una media su un campione parziale. Le dipendenze sono dichiarate nel `pyproject.toml` della root.
