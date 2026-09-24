# Golden Set Reviewer

Interfaccia locale per confrontare la pagina PDF originale, modificare il golden set e ispezionare le predizioni normalizzate dei parser.
Richiede PDF e annotazioni locali: questi dati non sono inclusi nella repository pubblica.

## Avvio

```bash
.venv-docling/bin/python benchmark/reviewer/server.py
```

Aprire [http://127.0.0.1:8765](http://127.0.0.1:8765).

## Funzioni

- navigazione tra tutte le pagine del manifest;
- rendering automatico della pagina PDF originale;
- modifica, riordino, aggiunta ed eliminazione dei blocchi golden;
- controllo di tipo, inclusione nell'EPUB, livello dei titoli e linguaggio del codice;
- confronto con ogni parser presente in `benchmark/results/golden-v0/predictions/`;
- metriche e corrispondenze tra blocchi;
- salvataggio come bozza o pagina revisionata, con aggiornamento automatico del manifest.

Il server ascolta soltanto su `127.0.0.1` per impostazione predefinita. `Cmd+S` o `Ctrl+S` salva la pagina corrente come bozza.

Gli identificatori dei blocchi rimangono stabili dopo aggiunte e riordini, per conservare le relazioni figura-didascalia. Eliminare una didascalia rimuove i riferimenti relativi. Il server valida l'intero schema JSON e rifiuta riferimenti a didascalie inesistenti; dopo il salvataggio il client ricarica le metriche aggiornate.
