# Validazione del capitolo campione

Il capitolo *Meaningful Names* usa le pagine PDF 48–61 di *Clean Code*. La conversione attuale produce 130 blocchi: 83 paragrafi, 22 titoli, 16 listati, quattro elementi di lista, tre figure e due didascalie. Le quattro note sono collegate al richiamo nel testo e al relativo ritorno.

La verifica automatica comprende:

- firma semantica esatta del contenuto e del CSS;
- compatibilità dei colori con temi chiari e scuri gestiti dal lettore;
- suddivisione dello spine sui segnalibri principali del PDF e collegamenti validi fra documenti;
- recupero delle righe e dell'indentazione dei listati dalle coordinate PDF;
- hash, dimensioni intrinseche e larghezza relativa delle immagini;
- gerarchia dell'indice e integrità dei collegamenti alle note;
- struttura ZIP, manifest, spine, XML e risorse dichiarate;
- EPUBCheck 5.4.0;
- reflow in Chrome desktop e mobile, senza overflow orizzontale.

La versione precedente è passata in EPUBCheck 5.4.0 con zero errori e zero warning. La build corrente con copertina e capitoli separati passa il validatore strutturale locale; EPUBCheck non è stato ripetuto perché in questo ambiente non è installato un runtime Java. Il report macchina, quando il controllo ufficiale viene eseguito, è scritto accanto all'EPUB in `output/epub/clean-code-meaningful-names/epubcheck.json`.

Questa validazione copre il capitolo campione e non dimostra che ogni PDF digitale o scansionato sia interpretato correttamente. Le modifiche al parser devono passare anche il golden set e, quando introducono nuovi tipi di documento, richiedono nuovi campioni annotati.
