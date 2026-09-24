# Profilo di tempo, memoria e dipendenze

Rapporto storico su campioni locali. I PDF e le tracce grezze non sono inclusi nella repository; le misure qui riportate non sono una soglia universale.

Misure eseguite il 21 settembre 2026 su MacBook Pro M5 Pro con 24 GB di memoria,
macOS 26.5 arm64 e Python 3.12.13. Ogni ripetizione parte da un processo nuovo;
i modelli sono già presenti nella cache locale. Il campionatore legge RSS, CPU,
thread e memoria virtuale ogni 10 ms e registra gli intervalli delle singole fasi.
`ru_maxrss` viene conservato come controllo indipendente del picco campionato.

PyTorch è compilato con MPS ma, in questo ambiente, `torch.backends.mps.is_available()`
restituisce `False`. Tutte le misure seguenti sono quindi CPU. TableFormer viene
comunque forzato su CPU dalla versione corrente di Docling.

## Campioni e garanzia di qualità

Questi profili sono stati raccolti immediatamente prima dell'aggiunta della
copertina. Le fasi neurali e le conclusioni sulla memoria non cambiano; gli hash
riportati in questa sezione identificano gli EPUB misurati in quel momento. Il
contratto corrente con copertina è
`614bca1f417600ebed7431e310b412dd002a692786e1ad8c41948a4f6e2f7852`.

Il caso principale converte le pagine 48–61 di Clean Code. Ogni esecuzione viene
confrontata con la firma esatta
`117bcb99e05b882f86ec217f6e6c0efd4ccfdaf5c707a2658b47cd76fd0194e8`.

Il controllo più ampio usa l'array dei tre PDF e le pagine 35–50 di ciascuno,
per 48 pagine complessive. Le tre firme risultanti sono rimaste identiche in
tutte le ripetizioni:

- Clean Code: `76bcd8fac0cd8ea8a2b9b42006a66229107aec06ca4f9dfc2af3fc1ce3f4906d`;
- Designing Data-Intensive Applications: `48da68a8cd35e2c9709633185cbb2ea312e6b94aa174523a8049b544e7c1bfc7`;
- Linguaggio C: `a4d3e505068f3c1661961f213c2c8d96a3a71f11e576008f3b0de7be7fc535a0`.

Queste firme garantiscono la stabilità tra le configurazioni misurate. Per i
due libri che non hanno ancora un contratto annotato completo, non sostituiscono
la futura golden suite semantica.

## Risultati ripetuti

Ogni riga riporta la mediana di tre processi; tra parentesi è indicato
l'intervallo osservato.

| Scenario | Pagine | Picco RSS | Tempo totale |
| --- | ---: | ---: | ---: |
| Clean Code, layout batch 4 | 14 | 2.889,1 MB (2.888,0–2.890,6) | 8,028 s (7,859–8,053) |
| Clean Code, layout batch 2 | 14 | 2.030,6 MB (2.013,0–2.035,5) | 8,624 s (8,212–10,120) |
| Clean Code, layout batch 1 | 14 | 1.544,5 MB (1.543,8–1.547,9) | 7,875 s (7,805–8,045) |
| Clean Code, batch 4, tabelle disabilitate | 14 | 2.740,9 MB (2.738,7–2.743,7) | 7,826 s (7,541–8,668) |
| Clean Code, batch 4, coda 4 | 14 | 2.858,9 MB (2.857,7–2.868,9) | 8,424 s (7,904–10,390) |
| Tre libri, layout batch 4 | 48 | 4.047,6 MB (4.024,6–4.057,5) | 20,036 s (19,035–20,588) |
| Tre libri, layout batch 1 | 48 | 2.816,8 MB (2.796,8–2.826,9) | 20,299 s (20,169–20,861) |

Sul capitolo, batch 1 riduce il picco di 1.344,6 MB, cioè il 46,54%, senza
peggioramento misurabile del tempo mediano. Sui tre libri la riduzione è di
1.230,9 MB, cioè il 30,41%, con un aumento del tempo dell'1,31%.

Ridurre la coda da 100 a 4 mantenendo batch reali da quattro cambia il picco
solo dell'1,05%. Una coda da uno produce invece batch effettivi da uno e non è
quindi una misura indipendente della memoria delle code.

## Attribuzione

Nel processo Clean Code con batch 4:

| Fase | Mediana |
| --- | ---: |
| Import del runtime Docling e del progetto | 2,623 s |
| Inizializzazione pipeline e modelli | 1,789 s |
| Conversione PDF con i modelli | 3,068 s |
| RSS dopo inizializzazione | 657,5 MB |
| Picco RSS | 2.889,1 MB |
| RSS dopo rilascio del risultato | 1.195,4 MB |

L'inizializzazione del modello Heron richiede circa 1,63 s e raggiunge circa
512,8 MB RSS. TableFormer `fast` richiede circa 0,13 s; tenerlo caricato aumenta
l'RSS stabile dopo l'inizializzazione di circa 145 MB. Sul capitolo, che non
contiene tabelle, disabilitarlo riduce il picco di 148,2 MB.

La situazione cambia nel campione Linguaggio C. In quelle pagine TableFormer
viene realmente eseguito: una predizione impiega circa 3,5–3,7 s e aggiunge
circa 767–771 MB al processo. Il layout riceve immagini da 595×842 pixel. Il
primo batch da quattro porta circa 2 megapixel nel modello e aggiunge circa
1,35 GB; con batch uno l'aumento iniziale è circa 0,87 GB.

Il picco dei tre libri è causato soprattutto dal terzo documento, non dalla
sola conservazione dei risultati precedenti. Elaborare ed esportare ogni
risultato prima di chiedere il successivo riduce il picco osservato da 4.190,8
MB a circa 4.025 MB nel singolo confronto disponibile. Dopo l'intero array,
l'RSS rimane elevato: mediana 2.748,7 MB con batch 4 e 2.426,0 MB con batch 1.
Una parte consistente delle allocazioni native del runtime non torna quindi al
sistema durante la vita del processo.

Disabilitare le immagini complete di pagina non cambia il picco perché Docling
deve ancora conservare le immagini necessarie alle figure. Riduce però gli
artefatti temporanei del capitolo da 5.909.218 a 1.361.462 byte, mantenendo la
stessa firma qualitativa.

## Import e spazio su disco

Gli import sono stati misurati in processi separati, tre volte per modulo.

| Import | Tempo mediano | Incremento picco RSS |
| --- | ---: | ---: |
| `torch` | 0,557 s | 176,0 MB |
| `transformers` | 0,974 s | 48,5 MB |
| `docling.document_converter` | 2,459 s | 345,7 MB |
| `numpy` | 0,023 s | 11,2 MB |
| `PIL.Image` | 0,011 s | 5,3 MB |
| adapter EPUB del progetto | 0,004 s | 3,2 MB |

L'ambiente Docling contiene 32.037 file, 1.152.082.313 byte logici e
1.238.478.848 byte allocati. La cache dei modelli contiene 530.010.645 byte:

- repository Heron: 171.764.371 byte;
- repository Docling Models: 358.236.323 byte, inclusi TableFormer `fast` e
  `accurate`;
- peso Heron effettivamente usato: 171.658.996 byte;
- peso TableFormer `fast` effettivamente usato: 145.453.276 byte.

I pacchetti più grandi dell'ambiente sono PyTorch 499,7 MiB, OpenCV 119,3 MiB,
SciPy 67,2 MiB, Transformers 47,1 MiB e pandas 37,1 MiB. Questa misura riguarda
la distribuzione su disco; non implica che ogni pacchetto contribuisca al picco
RSS.

## Conseguenze per il progetto

I dati separano tre problemi:

1. le attivazioni del layout crescono fortemente con il batch;
2. TableFormer occupa memoria anche nei documenti senza tabelle e ha un secondo
   picco importante quando viene eseguito;
3. il runtime CPU conserva una parte rilevante delle allocazioni dopo ciascun
   documento.

Prima di riscrivere l'inferenza, il confronto corretto dovrà quindi misurare
separatamente Heron e TableFormer, includere un documento con tabelle e
controllare la memoria residente dopo più documenti. La sola riduzione delle
dipendenze su disco non può spiegare né risolvere il picco di inferenza.

## Riproduzione

Il profiler completo è `benchmark/profile_docling.py`; inventario e costi di
import sono prodotti rispettivamente da `benchmark/inventory_runtime.py` e
`benchmark/profile_imports.py`. I profili grezzi e il riepilogo consolidato
sono in `benchmark/profiles/`.

```bash
.venv-docling/bin/python benchmark/profile_docling.py \
  --source samples/clean-code-robert-c-martin.pdf \
  --pages 48-61 --device cpu \
  --quality-baseline tests/fixtures/meaningful-names-quality.json \
  --output benchmark/profiles/current-cpu-b4.json

.venv-docling/bin/python benchmark/summarize_profiles.py \
  --output benchmark/profiles/summary.json
```
