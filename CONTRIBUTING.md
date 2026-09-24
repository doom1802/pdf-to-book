# Contribuire

Apri una issue per descrivere bug o proposte importanti prima di modificare il formato `book.json` o il comportamento della CLI. Per una correzione piccola, puoi aprire direttamente una pull request.

## Ambiente di sviluppo

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m unittest discover -s benchmark/golden -p 'test_*.py' -v
python benchmark/public_golden/run.py
```

Per provare la conversione completa, installa `python -m pip install -e '.[convert]'`. I modelli Docling possono richiedere un download. I test di integrazione che usano documenti locali non sono necessari per una pull request che tocca solo codice indipendente dai campioni.

Accompagna le modifiche di comportamento con un test che descriva l'effetto osservabile. Mantieni separati refactoring e modifiche funzionali quando possibile; spiega nella pull request come hai verificato il risultato e quali limiti rimangono. Per cambiamenti al formato EPUB, valida un output con EPUBCheck quando disponibile.

Non aggiungere documenti di terzi o loro derivati senza diritti di redistribuzione verificati. Le nuove fixture pubbliche vanno nel [corpus golden](benchmark/public_golden/README.md) con attribuzione, licenza, hash e annotazioni revisionate; esegui anche il gate `--live` se cambia l'estrazione. Non aggiungere output EPUB, cache dei modelli, profili locali o credenziali.
