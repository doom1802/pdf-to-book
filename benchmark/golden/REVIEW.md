# Registro della seconda revisione

Data: 18 settembre 2026.

La revisione è stata eseguita direttamente sui rendering delle pagine, a risoluzione originale, senza usare gli output dei parser come fonte della verità di riferimento.

## Completamento del 21 settembre 2026

La stessa procedura è stata applicata alle altre sei pagine del manifest:

- Clean Code PDF 50: verificati due esempi Java, titolo, prosa, intestazione, numero pagina e nota;
- Clean Code PDF 100: verificati continuazione di codice, Javadoc con HTML letterale, titoli e artefatti;
- DDIA PDF 35: verificati continuazione iniziale, lista, nota e footer;
- DDIA PDF 75: verificati query Cypher, lista numerata, cambio sezione, continuazioni e footer;
- Linguaggio C PDF 10: verificati continuazioni, codice, tabella dei tipi e numero pagina; corretta la chiusura della stringa nel `printf`;
- Linguaggio C PDF 50: verificati programma C, paragrafi sullo `switch`, esercizio, cambio sezione e numero pagina.

Tutte le nove annotazioni del manifest sono ora `reviewed`.

## Clean Code - pagina PDF 35

- verificati numero di pagina e intestazione ricorrente come elementi esclusi dall'EPUB;
- verificati i tre blocchi testuali e il titolo di sezione;
- verificati presenza, posizione logica e ordine di figura e didascalia;
- ampliata la descrizione della figura includendo assi e andamento della curva;
- nessuna correzione al testo trascritto.

Esito: `reviewed`.

## Designing Data-Intensive Applications - pagina PDF 25

- verificati etichetta e titolo del capitolo;
- verificati epigrafe e attribuzione come blocchi distinti;
- verificati i cinque elementi della lista e il loro ordine;
- verificate le ricomposizioni `technology`, `provide`, `processing`, `successful` e `building` dalle sillabazioni di fine riga;
- nessuna correzione al testo trascritto.

Esito: `reviewed`.

## Linguaggio C - pagina PDF 7

- verificati titolo del capitolo e titolo di sezione;
- verificati tutti i paragrafi e la ricomposizione delle parole spezzate dal text layer;
- verificati separatamente esempio, programma C, comando di compilazione, comando di esecuzione e output;
- ripristinati i due spazi visibili fra `#include` e `<stdio.h>`;
- confermata l'esclusione del numero di pagina.

Esito: `reviewed`.

## Correzione al valutatore

La descrizione editoriale di una figura non è testo sorgente presente nella pagina. È stata quindi esclusa da `text_accuracy`; presenza e didascalia della figura continuano a essere valutate con metriche dedicate.

## Limiti non coperti da questa revisione

Il formato attuale non annota ancora in modo puntuale corsivo, grassetto, codice inline, collegamenti o bounding box. Questi aspetti non devono essere considerati implicitamente corretti e richiedono un'estensione separata dello schema.
