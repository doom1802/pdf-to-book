# PDF to Book

Conversione locale di PDF digitali con text layer in EPUB 3, con una pipeline separata:

```text
PDF → Docling JSON → documento intermedio book.json → EPUB 3
```

Il risultato include una copertina ricavata dalla prima pagina, immagini dimensionate in proporzione alla pagina originale, indice navigabile, gerarchia dei titoli, codice ricostruito dalle coordinate del PDF e note con collegamenti di ritorno. Nei libri completi, i segnalibri di primo livello del PDF diventano documenti EPUB separati. I colori del testo e della pagina restano sotto il controllo del tema del lettore.

**Stato:** prototipo verificato su campioni locali e su un [corpus pubblico con licenze di redistribuzione](benchmark/public_golden/README.md). La qualità della conversione dipende dalla struttura del PDF. I PDF personali, gli estratti non autorizzati e gli EPUB generati restano locali. Converti soltanto documenti per i quali hai i diritti necessari.

## Avvio

Richiede Python 3.12 o successivo. In un nuovo ambiente:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[convert]'
pdf-to-book /percorso/al/tuo-documento.pdf \
  --pages 1-10 --title 'Il mio documento' --language it \
  --device cpu --output output/il-mio-documento.epub
```

Le dipendenze dell'estrazione sono nell'extra `convert`. Per lavorare soltanto su un JSON Docling già disponibile basta `python -m pip install -e .`. I modelli Docling vengono scaricati al primo utilizzo. Il percorso corrente usa il text layer e disabilita OCR: i PDF scansionati richiedono un'estensione separata.

`--device auto` seleziona un dispositivo disponibile; `--device cpu` funziona anche quando MPS non è accessibile. Se esiste, la cache locale `benchmark/cache/huggingface` viene riutilizzata. `HF_HUB_OFFLINE=1` evita accessi alla rete quando i modelli sono già in cache.

Per i PDF con equazioni isolate, `--enrich-formulas` attiva il modello Docling
CodeFormulaV2. Le formule riconosciute vengono esportate come MathML; se il
LaTeX è vuoto o non convertibile, la formula viene ritagliata dal PDF come
immagine, così non sparisce dall'EPUB. Il modello aggiuntivo viene scaricato
al primo utilizzo e può rendere la conversione sensibilmente più lenta su CPU.
Le equazioni MathML con più espressioni separate da `\quad` vengono impaginate
su righe distinte per evitare che escano dai margini nei lettori EPUB.
Quando un listato con simboli matematici non può essere ricostruito fedelmente
dalle coordinate dei caratteri, viene usato un ritaglio ad alta risoluzione del
PDF, con la trascrizione Docling come testo alternativo.
Questa opzione richiede una nuova estrazione Docling: non modifica un JSON
passato tramite `--docling-json`. La matematica inserita nei paragrafi resta
vincolata al text layer del PDF e può perdere pedici o altri dettagli.

La prima pagina del PDF viene usata come copertina anche quando `--pages` parte
da una pagina successiva. `--cover-page N` sceglie un'altra pagina;
`--no-cover` disabilita la copertina.

Per riutilizzare un export esistente, aggiungere:

```bash
--docling-json /percorso/al/docling-export.json
```

Il JSON deve contenere esattamente le pagine richieste e riferirsi allo stesso PDF. Non spostare le immagini referenziate separatamente dal loro export.

## Risultati

Accanto al file `.epub`, la cartella con lo stesso nome contiene:

- `book.json`: contenuti, provenienza nel PDF, risorse e avvisi di conversione;
- `cover.xhtml`, `content.xhtml` oppure `chapter-*.xhtml`, `nav.xhtml`, `style.css`, `assets/`: copertina e contenuto effettivamente inclusi nell'EPUB;
- `preview.html`: anteprima del contenuto con lo stesso stile dell'EPUB;
- `validation.json`: esiti dei controlli strutturali e conteggi;
- `epubcheck.json`, quando richiesto: rapporto del validatore ufficiale.

L'anteprima nel browser verifica il reflow; il comportamento nei singoli lettori EPUB può variare.

## Verifica

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m unittest discover -s benchmark/golden -p 'test_*.py' -v
python benchmark/public_golden/run.py
```

I test rapidi usano anche PDF pubblici con licenza CC BY, una fixture originale e
snapshot Docling versionati. La CI esegue inoltre `python
benchmark/public_golden/run.py --live` per rifare l'estrazione sui medesimi PDF.
I test sui documenti personali vengono saltati quando quei file non sono presenti.
Il rapporto della validazione campione è in [`docs/VALIDATION.md`](docs/VALIDATION.md).

Il validatore locale controlla ZIP, metadati, manifest, spine, XML, risorse, identificatori e destinazioni dei collegamenti. Per il controllo di conformità completo, scaricare [EPUBCheck ufficiale](https://github.com/w3c/epubcheck/releases) e aggiungere alla conversione:

```bash
--epubcheck /percorso/epubcheck.jar --java /percorso/java
```

La conversione restituisce un errore se i controlli falliscono. Il validatore locale non sostituisce EPUBCheck.

Prima delle ottimizzazioni, eseguire anche la quality gate esatta e il benchmark descritti in [`docs/performance.md`](docs/performance.md). Il contratto controlla contenuto, struttura, listati, note, immagini e CSS; con `SOURCE_DATE_EPOCH` verifica inoltre che due build equivalenti producano EPUB identici byte per byte.

## Benchmark e revisore

Il [golden set pubblico](benchmark/public_golden/README.md) controlla otto pagine
selezionate da tre PDF e verifica l'EPUB finale. Le annotazioni sono state
trascritte da pagine renderizzate; i JSON Docling sono input riproducibili, non
la verità di riferimento. La matrice di copertura e i difetti ancora aperti
sono documentati nel corpus. Un campione finito non può garantire ogni PDF.

Il golden set locale precedente comprende nove pagine annotate, tre per libro.
Le sue annotazioni e gli output dei parser non vengono distribuiti. Se possiedi
i documenti e gli output necessari, puoi rigenerare le predizioni e i risultati:

```bash
python benchmark/golden/run_benchmark.py
```

I risultati aggiornati sono in [`benchmark/golden/RESULTS.md`](benchmark/golden/RESULTS.md). La normalizzazione conserva codice letterale e indentazione; la presenza di una figura è distinta dalla verifica dei suoi contenuti. Gli hash di riferimento delle figure non sono ancora annotati, quindi quella metrica resta non disponibile.

```bash
python benchmark/reviewer/server.py
```

Aprire <http://127.0.0.1:8765>. I blocchi mantengono identificatori stabili durante il riordino e i punteggi si aggiornano dopo il salvataggio.

## Limiti del prototipo

La gerarchia dei titoli e alcune note vengono ricostruite anche dalla geometria: sono euristiche, validate sul capitolo campione, non una garanzia per ogni libro. Le continuazioni di codice tra pagine vengono segnalate per revisione, senza inventare rientri. Corsivo, grassetto e codice inline non sono ancora ricostruiti integralmente dal PDF. Il corpus pubblico include tabelle complesse e documenta le associazioni di celle che Docling ancora interpreta male. Le pagine di indice stampato con celle incoerenti vengono preservate come immagini leggibili.

Architettura e formato intermedio sono descritti in [`docs/architecture.md`](docs/architecture.md).
Per contribuire, leggi [`CONTRIBUTING.md`](CONTRIBUTING.md); le priorità di pulizia sono in [`docs/OPEN_SOURCE_ROADMAP.md`](docs/OPEN_SOURCE_ROADMAP.md).
Il codice è distribuito con licenza [MIT](LICENSE); le licenze delle fixture sono indicate in [`benchmark/public_golden/ATTRIBUTION.md`](benchmark/public_golden/ATTRIBUTION.md).
