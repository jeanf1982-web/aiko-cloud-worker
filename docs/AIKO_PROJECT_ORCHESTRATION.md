# AIKO — isolamento degli incarichi e apprendimento operativo

## Ambito
Queste regole si applicano solo al progetto AIKO. Non effettuano operazioni in progetti esterni, non leggono database altrui e non possono avviare processi su ACER.

## Controllo preliminare obbligatorio
Ogni incarico deve dichiarare `owner_project: AIKO`, `data_class: PUBLIC_SYNTHETIC`, `sensitivity: PUBLIC`, `approved_cloud: true` e una destinazione consentita. Se una proprietà manca, è sconosciuta o è conflittuale, il worker rifiuta prima di eseguire la funzione.

## Esecutore e continuità
I workflow GitHub cloud di calcolo dispongono di un gruppo di concorrenza con `cancel-in-progress: false`. Impediscono sovrapposizioni dello stesso worker; **non garantiscono di per sé esecuzione exactly-once fra run completati**. I lavori che richiedono esattamente una consegna devono avere un lease, una ricevuta e una barriera di deduplicazione persistente verificata separatamente.

## Gestione degli errori
Lavoro respinto: `HOLD_AND_REVIEW_WITH_PROJECT_OWNER`. Nessun trasferimento a un altro progetto, nessuna assegnazione implicita, nessun pagamento, nessuna modifica della produzione e nessuna riparazione automatica senza evidenze autorizzative.

## Sicurezza degli input
GitHub Actions deve passare input di workflow attraverso variabili d'ambiente e argomenti shell tra virgolette; non deve costruire script shell interpolando direttamente input dell'utente. Il controllo di firma Ed25519 resta un ulteriore livello di difesa ed è precedente all'esecuzione del lavoro nel codice Python.

## Certificazione
Il quality gate indipendente esegue 300 casi sintetici di proprietà/privacy e 300 di ripresa/rollback B8-003, oltre ai controlli statici sul workflow. Non certifica una vera consegna Growth in produzione; B8 non può essere promosso sulla base di questi risultati.

## Separazione di responsabilità
Qualunque incarico proveniente da un progetto differente viene respinto senza leggerne il payload. La rispettiva équipe, chat o pipeline proprietaria deve gestirlo nel proprio ambiente. Il coordinamento avviene tramite una nota umana di handoff, non condividendo tabelle, credenziali o processi.
