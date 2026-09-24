# Pubblicare su GitHub

La repository Git locale è già inizializzata sul branch `main`. Crea su GitHub, nel tuo account personale, una repository **pubblica** chiamata `pdf-to-book` (o con il nome che preferisci). Lasciala vuota: README, licenza e `.gitignore` sono già nel commit locale. [GitHub consiglia di non preselezionare questi file quando si importa una repository esistente](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository).

Nella cartella del progetto, collega la repo e invia il branch:

```bash
git remote add origin https://github.com/TUO_USERNAME/pdf-to-book.git
git push -u origin main
```

Se hai scelto un altro nome, sostituisci anche `pdf-to-book` nell'URL. Dopo il push, verifica che i file pubblici siano soltanto quelli mostrati da `git ls-files` e che la workflow **CI** sia verde. I file locali ignorati non vengono inviati da Git.
