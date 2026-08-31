# Roadmap — sessioni

> *Ipotesi di lavoro. Compagno di [TRAINER.md](TRAINER.md): quello dice **cosa** si costruisce e perché, questo dice **in che ordine** e dove si taglia.*

## Regola di taglio

Una **sessione** finisce con un binario che parte e che puoi esercitare. Non con un componente finito.

> **Se alla fine della sessione non c'è un comando da lanciare, la sessione è tagliata male.**

Ogni sessione si spacchetta in **non più di cinque issue**. Ogni issue si chiude con `/implement` in un contesto pulito, quindi deve stare in piedi da sola e puntare alle sezioni di TRAINER.md che le servono.

Una nota onesta sul senso di *«testabile dall'utente finale»*: fino alla sessione 5 l'utente finale sei **tu davanti a una CLI**, e quello che verifichi è che il motore risponda il vero. Dalla 5 in poi è qualcuno che vuole allenarsi, e quello che verifichi è la scheda. Il salto è alla 5, non prima, e va messo in conto.

## Il percorso

| # | versione | alla fine puoi |
|---|---|---|
| 1 | `0.1.0` | sfogliare 800 esercizi filtrando per attrezzo |
| 2 | `0.2.0` | interrogare il catalogo per pattern motorio e ampiezza |
| 3 | `0.3.0` | chiedere *«cosa posso fare oggi»* e ricevere l'insieme ammissibile |
| 4 | `0.4.0` | sapere quanto dura una selezione e cosa verrebbe tagliato |
| 5 | `0.5.0` | **ricevere una scheda vera** da un agente che non può sbagliare i vincoli |
| 6 | `0.6.0` | riportare la seduta in venti secondi e vedere lo stato muoversi |
| 7 | `0.7.0` | partire da zero: dieci domande, e in fondo la scheda della settimana 1 |
| 8 | `0.8.0` | attraversare le settimane — progressione, deload, rientro dalla pausa |
| 9 | `0.9.0` | essere ricordato: preferenze e vincoli sopravvivono alla sessione |
| 10 | `0.10.0` | vedere il sistema formulare un'ipotesi su di te e progettare la prova |
| 11 | **`1.0.0`** | **allenarti per otto settimane senza che il programma derivi** |

`1.0.0` è definito dal criterio di TRAINER.md: *stai ancora loggando, i carichi sono saliti, i fastidi non sono aumentati*. Tutto ciò che serve a reggere due mesi sta dentro. Tutto ciò che serve a **dimostrare** che il ciclo funziona sta dopo, ed è la sessione 12.

---

## Sessione 1 — `0.1.0` — Il catalogo grezzo

**Gira**: `trainer catalogo --attrezzo manubri` elenca gli esercizi.

1. Scheletro: pacchetto Python, SQLite con migrazioni versionate, CLI, layout `motore/` come libreria pura separata da tutto il resto.
2. Import di free-exercise-db in `esercizi` — campi nativi, istruzioni e immagini incluse, recuperabili per id.
3. Comando `catalogo` con filtri sui campi nativi.
4. Dump markdown del catalogo, versionato — la prima metà del meccanismo *«il DB è la verità, lo snapshot è la storia leggibile»*.

## Sessione 2 — `0.2.0` — Il catalogo arricchito

**Gira**: `trainer catalogo --pattern hinge --ampiezza-max spalla:flessione:120`.

1. Migrazione con i sette campi dell'appendice; `ampiezza_richiesta` strutturata come terna, non testo.
2. Prompt di arricchimento con output Pydantic e rifiuto di ciò che non valida.
3. Job a tre passate: due modelli economici di provider diversi, il forte solo sui disaccordi, voto di maggioranza.
4. Girata completa sugli ~800 + report dei disaccordi residui.
5. Verifica a mano su 50 righe campionate, e i filtri nuovi esposti sulla CLI.

> Il campo che vale la verifica a mano è `pattern_motorio`: se sbaglia lì, ogni conteggio di volume a valle è sbagliato e non te ne accorgi.

## Sessione 3 — `0.3.0` — L'insieme ammissibile

**Gira**: `trainer ammissibili --attrezzi corpo-libero --tempo 45 --escludi spinta_verticale`.

1. Tabelle `profilo` e `stato_pattern`, con le esclusioni e la loro data di ri-test.
2. `insieme_ammissibile(esclusioni, attrezzi, budget)` — il `WHERE` di TRAINER.md, funzione di libreria.
3. Unit test **senza alcun LLM**: un pattern escluso non compare mai, un attrezzo assente non compare mai, un'esclusione scaduta smette di escludere.
4. Il comando che la espone.

## Sessione 4 — `0.4.0` — Tempo

**Gira**: dai una selezione, ti dice quanto dura e cosa toglierebbe per starci in 40 minuti.

1. Modello di durata: `Σ [ setup + serie × (lavoro + recupero) ]`, recuperi dallo schema, setup dal catalogo.
2. `budget_residuo` e `simula_taglio`, con l'ordine isolamenti → pattern secondari → serie sui primari.
3. Test che il taglio **non tocchi mai i recuperi**, in nessun ramo.
4. `storico_pattern` e `carico_ultima_esecuzione` su stato ancora vuoto — devono rispondere «non so», non rompersi.
5. Wrapper MCP sulla libreria. Mezza giornata, e da qui in avanti ispezioni il motore da un client generico mentre sviluppi.

> L'MCP è anticipato rispetto a TRAINER.md apposta: costa poco e il ritorno è tutto nelle sessioni successive, quando l'agente comincia a sbagliare e vuoi vedere cosa vede lui.

## Sessione 5 — `0.5.0` — La prima scheda

**Gira**: `trainer scheda` e ti arriva un allenamento che puoi fare stasera.

La sessione più grande e la meno divisibile: l'agente senza il validatore non è consegnabile, quindi restano insieme.

1. La superficie di tool esposta all'agente — wrapper sottili sulla stessa libreria, zero logica nuova.
2. Nodo agente che cicla sui tool, con **budget di chiamate**; a budget esaurito **emette comunque**.
3. Output strutturato: l'agente emette `(id, serie, ripetizioni)`, mai prosa. Il motore rende la scheda.
4. Validatore deterministico in uscita: id fuori dall'insieme → rifiuto. Dieci righe.
5. Le sei invarianti sulle sei situazioni avverse di TRAINER.md. **Metrica: 100%.** Sotto è un bug, non una regolazione.

## Sessione 6 — `0.6.0` — Il log per deviazione

**Gira**: fai la seduta, scrivi *«panca ok, solo 3 serie di military, spalla 4 su 10»*, e lo stato si muove.

1. Tabella `sedute`; il default è l'aderenza, si riporta solo la deviazione.
2. Parsing conversazionale → righe strutturate, con conferma quando è ambiguo.
3. Volume contato **sul pattern eseguito**, mai sul previsto; `stato_pattern` aggiornato di conseguenza.
4. `storico_pattern` e `storico_aderenza` veri, più il **deficit di volume** come grandezza unica.

> Va provato subito il caso che TRAINER.md dichiara centrale: **saltare due settimane**. Il motore deve assumere l'aderenza e segnalare l'incertezza, non bloccarsi.

## Sessione 7 — `0.7.0` — Onboarding

**Gira**: da database vuoto a scheda della settimana 1, in una conversazione sola.

1. Grafo multi-turno su LangGraph con checkpointing: rispondi a metà, torni domani, riparti dalla domanda 7.
2. Le dieci-dodici domande, nell'ordine di TRAINER.md — obiettivo per primo, acciacchi per ultimi.
3. Obiettivo primario forzato a uno; gli altri diventano vincoli. Due obiettivi in conflitto → l'agente lo dice e fa scegliere.
4. Triage sui **movimenti**, mai sui sintomi: produce esclusioni con data di ri-test, non diagnosi. Più l'innesco medico.
5. Test del vincolo non negoziabile: **LangGraph non persiste dominio, SQLite non persiste conversazione**.

## Sessione 8 — `0.8.0` — Il tempo lungo

**Gira**: la settimana 4 è diversa dalla 1, e se sparisci tre settimane il rientro è graduale.

1. Tabella `mesociclo`: l'agente sceglie lo schema e **dichiara perché**.
2. I due schemi di v1 — doppia progressione e autoregolato su sensazione.
3. Rientro dalle date: ≤10 giorni niente, 11-21 un rodaggio, 22-45 due, oltre calibrazione piena.
4. **Il documento metodologico.** Sintesi curata a mano con le fonti in linea, iniettata per intero al confine del mesociclo. Lavoro umano, non generabile.
5. `decisioni` append-only: ogni cambio, una riga, col motivo.

> L'issue 4 non è in «Primi passi» di TRAINER.md pur essendo dentro allo scope v1. È l'unica cosa su cui l'agente delibera al confine del mesociclo: senza, la sessione 8 consegna un motore di progressione, non un allenatore.

## Sessione 9 — `0.9.0` — Conclusioni

**Gira**: gli dici che odi le spinte, e alla settimana 6 se lo ricorda ancora.

1. Tabella `conclusioni` e la **regola d'ingresso**: ha una fonte? Validatore da dieci righe, in linea, entra come *provvisoria*.
2. L'agente decide a ogni turno cosa va ricordato — e il *perché*, non solo la frase.
3. `conclusioni_attive()` come tool, riletto **prima di ogni scelta**.
4. Ciclo di vita: stati, ritiro con motivo, contatore di utilizzi.
5. Il test che separa i due depositi: `decisioni` si legge per ricostruire, `conclusioni` per decidere. Una conclusione dedotta senza fonte deve essere **rifiutata**.

## Sessione 10 — `0.10.0` — Ipotesi, prova, esito

**Gira**: *«gli affondi non mi vanno»* → il sistema non conclude, progetta una prova.

1. Tabelle `ipotesi` e `prove`; la forma vincolata: **ammissibile solo se esiste una prova che la discrimina**.
2. La prova come modifica alla scheda che tiene ferme tutte le variabili tranne una, con una durata.
3. Macchina a stati su LangGraph: nasce in una seduta, vive due settimane, si chiude in un'altra.
4. L'esito **rientra**: alla seduta dopo il sistema sa qualcosa che prima non sapeva, e sa di aver sbagliato se ha sbagliato.
5. Instradamento: un'ipotesi senza prova possibile non è falsa, è fuori dal programma → all'utente o al medico.

## Sessione 11 — `1.0.0` — Il supervisore

**Gira**: il ciclo completo, e adesso è sicuro tenerlo acceso otto settimane.

1. **Golden set**: 40-60 esempi etichettati a mano, asse A e asse B. Falsi positivi sulle righe «no» pesati doppio. Un esempio che non sai etichettare non entra.
2. Passata su LangGraph **tra** le sedute, innescata dalle date all'apertura della conversazione. Latenza zero sul percorso caldo.
3. Isolamento verificato: vede forma della traiettoria, obiettivo, conclusioni attive — **mai la prosa dell'agente**.
4. Gate del consolidamento: conferma, fonde, marca sospetta, ritira con motivo. Criterio unico, la coerenza.
5. I denti: osservazione iniettata → se l'agente fa uguale una seconda volta, si converte in un vincolo del motore. «L'ha ignorata» è decidibile, quindi lo verifica il codice.

> La riga più importante di tutta la suite è nell'issue 1: *stesso esercizio otto volte di fila perché è la preferenza dichiarata* → **non segnalare**. Rispettare una preferenza e derivare sono identici nei dati. Se il supervisore sbaglia questa, il sistema contesta all'utente ciò che l'utente ha chiesto, ed è insopportabile in due settimane.

---

## Dopo 1.0.0

| # | versione | cosa |
|---|---|---|
| 12 | `1.1.0` | **Livello 2** — utente simulato con verità nascoste, i due casi di controllo (utente senza verità, rumore), k=5 run, e l'insieme di regressione raccolto dai run |
| 13 | `1.2.0` | Server + bot Telegram. Puramente reattivo, nessuno scheduler. Il nucleo non cambia: non ha mai assunto niente sul client |
| 14 | `2.0.0` | Patologie diagnosticate; controllo dell'esecuzione via video |

La 12 è l'unica sessione che **non consegna niente all'utente finale**, e va detto. Consegna il diritto di fidarsi del ciclo. Sta dopo la 1.0.0 e non prima perché TRAINER.md è esplicito: il livello 2 si misura solo quando i componenti sotto passano, altrimenti misuri un ciclo costruito su pezzi di cui non sai niente — e i pezzi non passano tutti prima della sessione 11.

## Deviazioni dichiarate da TRAINER.md

| | «Primi passi» dice | qui | perché |
|---|---|---|---|
| golden set del supervisore | passo 1, prima di tutto | sessione 11 | è la scelta più discutibile di questo file: *«se il supervisore sbaglia qui tutto quello a valle è avvelenato»* resta vero. Ma il supervisore non gira fino alla 11, e sessanta righe scritte alla 1 verrebbero riscritte quando lo stato reale esiste. Il rischio è mitigato dal fatto che il gate d'ammissione (sessione 9) è codice, non modello |
| MCP | non compare | sessione 4 | costa mezza giornata e ripaga per sette sessioni |
| documento metodologico | assente da «Primi passi» | sessione 8, issue 4 | è nello scope v1 ma non aveva uno slot |

## Rischi

**La sessione 5 è più grossa delle altre e non si divide bene.** L'agente senza validatore non si consegna. Se sfonda, il taglio da fare è l'issue 5 (le invarianti) in una sessione `0.5.1` a sé — mai l'issue 4.

**Le sessioni 1-4 non hanno modelli dentro e le 5-11 sì.** Il ritmo cambia bruscamente: le prime sono deterministiche e veloci, dalla 5 ogni verifica diventa una distribuzione. Non stimare le seconde con la velocità delle prime.

**L'arricchimento (sessione 2) è l'unico punto con un costo esterno vero** e gira una volta sola. Vale la pena farlo girare prima su 30 esercizi e leggere i disaccordi a mano, prima di lanciarlo sugli 800.
