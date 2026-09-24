# Pubblicare su GitHub

La repository pubblica è già disponibile su [GitHub](https://github.com/doom1802/pdf-to-book) e il remote `origin` punta a questo indirizzo. README, licenza e `.gitignore` sono versionati.

Per inviare nuove modifiche dal branch `main`:

```bash
git status --short
git push origin main
```

Dopo il push, verifica che i file pubblici siano soltanto quelli mostrati da `git ls-files` e che la workflow **CI** sia verde. Il corpus golden pubblico ha licenze e attribuzione proprie; gli altri PDF locali ignorati non vengono inviati da Git.
