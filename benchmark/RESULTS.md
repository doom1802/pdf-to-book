# Risultati iniziali

Data del test: 17 settembre 2026.

## Ambiente

- MacBook Pro con Apple M5 Pro, 15 core e 24 GB di memoria;
- Python 3.12.13;
- MinerU 4.0.0, PaddleOCR 3.7.0 e Docling 2.128.0;
- prime 20 pagine di ogni PDF;
- elaborazione interamente locale.

Gli ambienti Python occupano circa 1,3 GB per MinerU, 1,0 GB per PaddleOCR e 1,2 GB per Docling. I modelli PaddleOCR-VL occupano circa 1,9 GB; quelli Docling usati nel test circa 506 MB. I modelli MinerU scaricati per il tier `standard` occupano circa 2 GB.

## Documenti

| Documento | Pagine totali | Text layer nelle prime 10 pagine |
| --- | ---: | ---: |
| Designing Data-Intensive Applications | 613 | 7/10 pagine con testo significativo |
| Clean Code | 462 | 6/10 pagine con testo significativo |
| Linguaggio C | 216 | 10/10 pagine con testo significativo |

Tutti e tre i campioni possiedono un text layer utilizzabile. Le pagine senza testo significativo nelle prime due opere sono principalmente copertine o pagine grafiche.

## Tempi

| Documento | MinerU `flash` | MinerU `standard` |
| --- | ---: | ---: |
| Designing Data-Intensive Applications | 32,32 s | 55,23 s |
| Clean Code | 7,94 s | 117,79 s |
| Linguaggio C | 3,84 s | 50,11 s |

Il primo avvio di ciascun percorso include costi di inizializzazione e non deve essere interpretato come throughput stabile. In particolare, Clean Code è stato il primo test `standard` e ha incluso il caricamento iniziale del modello.

## Tutti i tier MinerU

Su Clean Code sono stati provati anche gli altri due tier, sempre sulle prime 20 pagine.

| Tier | Tempo | Dimensione Markdown | Righe | Titoli Markdown | Immagini incorporate |
| --- | ---: | ---: | ---: | ---: | ---: |
| `flash` | 7,94 s | 188.966 B | 486 | 17 | 1 |
| `basic` | 14,84 s | 18.165 B | 468 | 6 | 0 |
| `standard` | 117,79 s | 18.662 B | 445 | 6 | 0 |
| `advanced` | 110,47 s | 20.229 B | 797 | 50 | 0 |

`advanced` non è risultato automaticamente migliore: ha separato più blocchi, ma ha trasformato molti elementi dell'indice in titoli Markdown, producendo una struttura eccessivamente frammentata. Il test conferma che il nome del tier non basta per scegliere il percorso migliore per un EPUB.

## Output Markdown

| Documento | Tier | Dimensione | Righe | Titoli Markdown | Immagini incorporate |
| --- | --- | ---: | ---: | ---: | ---: |
| Designing Data-Intensive Applications | `flash` | 1.936.346 B | 371 | 10 | 4 |
| Designing Data-Intensive Applications | `standard` | 486.494 B | 417 | 13 | 2 |
| Clean Code | `flash` | 188.966 B | 486 | 17 | 1 |
| Clean Code | `standard` | 18.662 B | 445 | 6 | 0 |
| Linguaggio C | `flash` | 62.656 B | 796 | 30 | 0 |
| Linguaggio C | `standard` | 149.247 B | 802 | 18 | 1 |

Le immagini sono incorporate nel Markdown come stringhe base64. Questo aumenta molto la dimensione del file, soprattutto nel risultato `flash` di Designing Data-Intensive Applications.

## Osservazioni qualitative

### MinerU `flash`

- è nettamente più veloce sui PDF con text layer;
- conserva molto testo senza usare il VLM;
- può produrre troppi titoli Markdown;
- può ereditare formattazioni problematiche dal PDF, come interi paragrafi in grassetto;
- può generare file molto pesanti quando incorpora immagini in base64.

### MinerU `standard`

- riconosce meglio alcuni titoli, copertine e strutture dell'indice;
- riduce il numero di falsi titoli in diversi casi;
- richiede molto più tempo;
- non corregge automaticamente tutti i problemi del text layer;
- nel campione Linguaggio C ha introdotto alcune spezzature nel testo, quindi non è sempre più fedele di `flash`.

### MinerU `basic` e `advanced`

- `basic` è più lento di `flash`, ma nel campione Clean Code produce una gerarchia più contenuta;
- `advanced` esegue un'analisi in più passaggi ed è molto più lento;
- nel campione Clean Code, `advanced` ha prodotto 50 titoli contro i 6 di `basic` e `standard`, soprattutto per sovrasegmentazione dell'indice;
- nessuno dei due sostituisce la necessità di valutare la qualità pagina per pagina.

## Parser alternativi

### Docling 2.128.0

Clean Code, prime 20 pagine:

| Pipeline | Tempo elaborazione | Tempo processo completo | Markdown | Titoli | Immagini referenziate |
| --- | ---: | ---: | ---: | ---: | ---: |
| `native` | 3,32 s | 24,99 s | 42.104 B | 0 | 2 |
| `standard`, cache calda, MPS, senza OCR | 6,07 s | 10,92 s | 86.975 B | 8 | 3 |

La pipeline `native` è molto veloce ma conserva troppe interruzioni di riga e non ricostruisce la gerarchia. La pipeline `standard` riconosce titoli, immagini e l'indice come tabelle. Oltre al Markdown esporta un documento JSON con struttura, provenienza e coordinate: questo la rende particolarmente interessante come formato intermedio per l'EPUB.

### PaddleOCR-VL 1.6

Test di fattibilità sulle prime 3 pagine di Clean Code, su CPU:

| Avvio | Tempo | Markdown | Titoli | Immagini referenziate |
| --- | ---: | ---: | ---: | ---: |
| iniziale, incluso download/caricamento | 253,08 s | 1.707 B | 3 | 1 |
| cache calda | 64,08 s | 1.707 B | 3 | 1 |

L'output è pulito e le immagini vengono salvate separatamente, ma su questo Mac il backend CPU è troppo lento per essere il percorso predefinito di un libro intero. Resta utile come fallback VLM su pagine difficili, scansioni o layout che i parser più veloci non ricostruiscono bene.

## Conclusione provvisoria

Non emerge un tier MinerU vincitore per ogni pagina. Per questi campioni, `flash` è una baseline molto forte e veloce, mentre `standard` può migliorare la struttura ma ha un costo elevato e può introdurre nuovi errori.

Docling `standard` è al momento il candidato più promettente come parser generale per PDF digitali: è veloce con MPS e offre un formato intermedio strutturato. MinerU `flash` rimane una baseline importante. PaddleOCR-VL è più adatto a un fallback selettivo che a un'elaborazione completa su CPU.

Prima di scegliere il comportamento definitivo servono:

1. pagine campione tratte dal corpo dei capitoli, non solo dal frontespizio;
2. test Docling sugli altri due libri e su pagine interne con codice e figure;
3. test di un ulteriore parser VLM, come Infinity-Parser2-Flash, se eseguibile in modo efficiente su Apple Silicon;
4. criteri di valutazione specifici per l'EPUB, soprattutto titoli, codice, immagini e ordine di lettura.
