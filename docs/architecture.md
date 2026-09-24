# Architettura del primo percorso EPUB

## Separazione delle responsabilità

`pdf_to_book.__main__` esegue Docling o riutilizza un JSON, controlla l'intervallo di pagine e coordina conversione e validazione. Nessun contenuto del PDF viene inviato a un servizio remoto.

`docling_adapter` segue l'albero di lettura nativo, conserva coordinate e riferimenti ai blocchi, esclude header/footer e copia le immagini. I caratteri dei listati sono estratti dai rettangoli identificati da Docling: le coordinate orizzontali ripristinano gli spazi e quelle verticali le righe. Il testo originale del parser rimane nel documento intermedio per confronto. Ogni differenza nei caratteri non bianchi genera un avviso.

Le formule isolate possono essere riconosciute dal modello opzionale CodeFormulaV2
di Docling. L'adattatore conserva il LaTeX e il testo originale del PDF. Se il
LaTeX è vuoto o produce marcatori di allineamento non validi, l'adattatore crea
un'immagine della regione corrispondente nel PDF. `epub` converte il LaTeX
utilizzabile in MathML e dichiara la proprietà `mathml` nel manifest del
capitolo; le formule con immagine restano nella medesima posizione di lettura.

La dimensione dei titoli è stimata dalle dimensioni effettive dei caratteri nel PDF, perché alcuni documenti dichiarano una dimensione font nominale di 1 e applicano una matrice di scala. Dimensioni distinte producono livelli ordinati. Le intestazioni dei listati vengono convertite in didascalie.

Le note esplicitamente classificate e i piccoli elementi numerati in fondo alla pagina sono raccolti separatamente. Il riferimento nel testo viene collegato soltanto se il marcatore ha una singola occorrenza candidata nella prosa della stessa pagina. I casi ambigui rimangono visibili e vengono segnalati.

I paragrafi incompleti vengono uniti solo tra pagine consecutive e senza un blocco semantico intermedio. I blocchi di codice che attraversano pagine rimangono distinti con un avviso. Una chiusura di codice separata su una stessa pagina può essere recuperata come un unico rettangolo con il blocco precedente, se immediatamente adiacente.

`epub` produce XHTML con escape XML, indice gerarchico, liste, immagini, tabelle, note e CSS per il reflow. La larghezza di ogni figura viene calcolata rispetto alla pagina PDF sorgente e applicata in percentuale nel contenuto reflowable; larghezza e altezza intrinseche mantengono il rapporto d'aspetto. Il contenitore include soltanto risorse locali dichiarate nel manifest. Gli hash delle immagini vengono ricontrollati prima del confezionamento.

Quando Docling classifica l'indice stampato come `document_index` ma ne fonde le voci in celle non affidabili, l'adattatore conserva la regione originale come immagine leggibile. L'indice EPUB navigabile rimane separato e viene costruito dai titoli; l'immagine mantiene visibile la pagina stampata senza attribuirle link o testo che il parser non ha ricostruito con certezza.

`validate` verifica la struttura e tutti i collegamenti interni. EPUBCheck è una seconda verifica indipendente, opzionale nella CLI. La validità del contenitore non equivale alla correttezza semantica del parsing.

## Formato intermedio `book-0.1`

| Campo | Contenuto |
| --- | --- |
| `schema_version` | `book-0.1`, distinto dallo schema del golden set |
| `title`, `author`, `language` | Metadati editoriali |
| `source`, `source_sha256`, `pages` | PDF originale, hash e pagine elaborate |
| `blocks` | Blocchi in ordine di lettura con `id`, `type`, `text`, `provenance` |
| `provenance` | Numero di pagina, rettangolo, origine delle coordinate e intervallo nativo Docling |
| `level`, `font_size`, `parser_level` | Gerarchia ricostruita e dati originali dei titoli |
| `parser_text`, `text_method` | Testo originale e metodo di ricostruzione dei listati |
| `source_text`, `number` | Testo PDF e numero delle formule riconosciute |
| `display_width_px` | Larghezza di lettura delle formule esportate come immagine |
| `joined_ids`, `joined_source_refs` | Traccia dei blocchi ricongiunti |
| `asset`, `image_sha256`, `caption_ids` | Immagine e relazioni alle didascalie |
| `display_width_percent`, `source_aspect_ratio` | Dimensione relativa alla pagina PDF e rapporto sorgente |
| `image_width_px`, `image_height_px` | Dimensioni intrinseche della risorsa esportata |
| `group_id`, `ordered`, `marker` | Appartenenza e numerazione delle liste |
| `data.table_cells` | Celle di tabella, posizioni e span |
| `note_refs` | Intervalli nel testo e destinazioni delle note |
| `footnotes` | Note con marcatore e collegamento di ritorno, quando identificabile |
| `assets` | Percorso relativo, media type e SHA-256 delle risorse |
| `warnings` | Ambiguità o differenze che richiedono revisione |
| `excluded_furniture` | Riferimenti alle intestazioni e ai footer esclusi |

Gli intervalli `note_refs` si riferiscono al testo finale del blocco. Gli intervalli `charspan` dentro la provenienza descrivono l'estrazione sorgente e non vanno interpretati come offset del testo finale ricostruito. Le immagini restano file separati dal JSON; distribuire insieme documento e risorse.

Questo formato è volutamente piccolo. Non rappresenta ancora tutti gli stili inline o tutti i tipi di relazioni editoriali di un libro complesso.

## Valutazione

Il benchmark continua a confrontare esportazioni Markdown omogenee. La pipeline EPUB usa il JSON nativo: i due percorsi hanno scopi diversi e non condividono implicitamente le stesse garanzie.

`figure_presence_recall` confronta la quantità di figure; `figure_recall` verifica identità SHA-256 solo sulle figure con riferimento golden verificato, accompagnata da `figure_verification_coverage`. Un hash diverso non stabilisce se due ricampionamenti siano visivamente equivalenti. Non viene inventato un riferimento usando la predizione da valutare.

Le specifiche di confezionamento seguite sono quelle di [EPUB 3.3](https://www.w3.org/TR/epub-33/).
