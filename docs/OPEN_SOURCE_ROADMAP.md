# Piano di rientro tecnico

Il primo rilascio pubblico privilegia installazione, verifiche ripetibili e confini chiari dei dati. Le attività sotto sono ordinate per rischio e dipendenze. Ogni fase può essere una pull request separata.

## P0 — Base pubblicabile

- [x] Escludere PDF, estratti, annotazioni di libri, modelli e output generati dal primo commit.
- [x] Rendere la suite eseguibile in un checkout pulito con test sintetici; lasciare opzionali i test su documenti locali.
- [x] Documentare installazione, limiti, contributi e istruzioni brevi per agenti.
- [x] Aggiungere CI per i test rapidi su Python 3.12.
- [x] Aggiungere una licenza esplicita e verificare il contenuto del primo commit.
- [x] Creare e collegare la repository GitHub pubblica; istruzioni in `docs/PUBLISHING.md`.

## P1 — Affidabilità e struttura

- [ ] Completare la sostituzione dei test di integrazione locali: il corpus pubblico ora copre note, codice, figure, tabelle e indice, ma mancano una formula isolata verificata, OCR, lingue non latine e documenti di grandi dimensioni.
- [ ] Separare parsing degli argomenti, invocazione di Docling e orchestrazione della pipeline; rendere gli errori della CLI consistenti e verificabili senza modelli.
- [ ] Definire e versionare lo schema di `book.json`, con validazione all'ingresso dell'EPUB e una procedura di migrazione per eventuali modifiche incompatibili.
- [ ] Suddividere `docling_adapter.py` ed `epub.py` per responsabilità, mantenendo test di regressione sul comportamento pubblico.
- [ ] Eliminare l'`expectedFailure` per le voci `document_index` dopo aver deciso come rappresentarle nel formato intermedio.

## P2 — Qualità misurabile

- [ ] Aggiungere controllo statico e formattazione automatici, applicandoli in una PR dedicata senza cambiare la logica.
- [ ] Eseguire EPUBCheck in CI su EPUB costruiti da fixture redistribuibili; documentare la matrice dei lettori provati manualmente.
- [ ] Misurare qualità e prestazioni su un corpus pubblico versionato, con baseline e criteri di accettazione chiari.
- [ ] Profilare memoria e tempi sulle nuove fixture, poi ottimizzare i colli di bottiglia misurati.

## P3 — Estensione del golden set pubblico

- [ ] Aggiungere una seconda revisione indipendente delle annotazioni e risolvere gli eventuali disaccordi prima di alzare le soglie.
- [ ] Correggere l'ordine dei blocchi in due colonne, i collegamenti delle note e l'associazione delle celle; convertire i difetti elencati in `benchmark/public_golden/README.md` in controlli CI obbligatori.
- [ ] Aggiungere PDF con licenza verificata per formule isolate, pagine ruotate, layout a tre colonne, testo da destra a sinistra, scansioni con OCR e documenti lunghi. Registrare nel manifest i diritti, l'hash e le pagine annotate.
- [ ] Misurare recupero del testo, precisione dei blocchi e ordine di lettura anche sul corpus pubblico, mantenendo le metriche separate dai controlli esatti dell'EPUB.

La pubblicazione del codice non implica che le conversioni di opere di terzi siano distribuibili. Ogni futuro corpus pubblico richiede una verifica della licenza del materiale sorgente e delle opere derivate.
