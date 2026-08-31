# REPS

> *Reasoning Engine for Personal Strength. v1 personale.*

## Principio

Ogni volta che si decide **se una cosa la fa il codice o la fa l'agente**, si guarda a quale categoria appartiene.

| categoria | chi | cosa |
|---|---|---|
| **analitico** | motore | deterministico, riproducibile, verificabile |
| ⤷ *vincolato* | | confini che l'agente non può **scavalcare**. Un confine spostabile non è un confine. |
| ⤷ *derivativo* | | grandezze che l'agente non deve **ricalcolare**: si ricavano da regole o da dati. Gli LLM producono numeri plausibili e sbagliati, e non te ne accorgi. |
| **deliberativo** | agente | giudizio, dentro lo spazio che l'analitico lascia libero |

> **L'analitico definisce lo spazio. L'agente si muove dentro.**

Questa regola esiste perché l'errore ricorrente in fase di progettazione è scrivere come regole di codice ciò che è una decisione dell'agente — trasformando un sistema agentico in una pipeline.

Da cui altre due regole operative, che dicono *come* si applica la prima senza ricadere nella pipeline.

### Vincola la forma, mai il contenuto

Il sistema garantisce una **forma verificabile**; l'agente riempie il **contenuto**.

| | il sistema garantisce | l'agente riempie |
|---|---|---|
| scheda | id ammissibile + serie + ripetizioni | quale, quanti, in che ordine |
| ipotesi | esiste una prova che la discrimina | cosa ipotizza, cosa tiene fermo |
| conclusione | ha una fonte | cosa dice |
| osservazione | esiste una misura che dice se è stata ascoltata | cosa osserva |

### Enumeri solo ciò che è già enumerato nel mondo

Gli esercizi sono un mondo chiuso: il catalogo esiste, è finito, ed è un fatto del dominio. Pre-calcolarne l'insieme ammissibile è corretto.

I motivi per cui una persona salta una seduta, le cose che le piacciono, le cause di un fastidio: mondo aperto. **Nessuno ha la lista.** Enumerare un mondo aperto ha una proprietà velenosa: quando la risposta vera è fuori lista non ottieni un errore, ottieni una risposta plausibile e sbagliata.

Il test da applicare a ogni pezzo che si progetta:

> **Ho enumerato in anticipo l'insieme delle risposte possibili?**
> Se sì, quello che ho costruito è un classificatore, non un agente.

### E sotto a tutto

> **Niente entra nel sistema se non si può verificare che fosse sbagliato.**

---

## Cos'è

Non un generatore di schede. **Un ciclo.**

Una scheda è un prompt: attrezzi + tempo + limitazioni → tabella. Il valore non sta nella generazione, sta nell'adattamento nel tempo: alla settimana 3 gli affondi in fondo alla seduta hanno fatto saltare tre allenamenti, e il sistema **cambia**.

Stato persistente, feedback dopo ogni seduta, progressione, deload, sostituzione.

### I vincoli non sono patologie

La maggior parte di ciò che limita una scheda non è medico:

- *«le spinte non mi piacciono»*
- *«la cyclette mi annoia»*
- *«il giovedì non ho tempo»*
- *«voglio finire entro le 19»*
- *«gli affondi mi stancano più di quanto rendano»*

Sono **più importanti** dei fastidi, perché si smette di allenarsi per noia molto più spesso che per dolore. I fastidi sono un caso particolare del problema generale — *l'utente ha preferenze, vanno rispettate e vanno capite* — non il caso centrale.

## Successo

Congiuntamente, a 8 settimane:

1. **stai ancora loggando** — collo di bottiglia reale: i progetti di fitness personale non muoiono per consigli sbagliati, muoiono perché smetti di registrare;
2. i carichi sui pattern principali sono saliti;
3. i fastidi non sono aumentati.

Il criterio 1 è il criterio del prodotto e richiede due mesi. Non è la dimostrazione che il sistema funziona: quella è nella sezione **Valutazione**, e si ottiene in un pomeriggio.

---

## Scope

**Dentro (v1)**: uso personale; preferenze e vincoli di ogni natura; fastidi e piccoli recuperi; catalogo arricchito; motore analitico esposto come libreria di tool; agente deliberativo che guida il ciclo; memoria con ciclo di vita; supervisore; documento metodologico; video dimostrativi; log conversazionale.

**Fuori, dichiarato**:

- **Patologie diagnosticate** (ernie, post-operatorio, patologie croniche) → **v2**. In v1: se l'utente dichiara una patologia, si consiglia il medico e si prosegue solo se insiste. In generale si consiglia sempre il medico quando l'utente lamenta dolori importanti.
- **Controllo dell'esecuzione via video** (pose estimation, valgo del ginocchio, ecc.) → **v2**. È un progetto più grande di tutto il resto.
- Nutrizione.
- Multi-utente e distribuzione (comporterebbe GDPR categoria particolare sui dati sanitari).

---

## Glossario

- **pattern motorio** — la classe di movimento, non l'esercizio. Undici valori: spinta orizzontale/verticale, trazione orizzontale/verticale, squat, hinge d'anca, monopodalico, core anti-estensione, core anti-rotazione, portata, isolamento. È il livello a cui si programma, si esclude e si contabilizza.
- **vincolo** — tutto ciò che limita la scheda: preferenza, tempo, attrezzatura, noia, fastidio. La maggior parte non è medica.
- **insieme ammissibile** — la risposta a una domanda che l'agente ha scelto di fare al motore: gli esercizi compatibili con esclusioni, attrezzatura di oggi e tempo disponibile. L'agente sceglie dentro; non lo allarga mai.
- **esclusione** — un confine **duro** del motore, riservato alla sicurezza: un pattern o un'ampiezza non prescrivibile, con una data di ri-test. Una preferenza non diventa mai un'esclusione — altrimenti muri un pattern per sempre e nessuno potrà riaprirlo.
- **ipotesi** — un'affermazione falsificabile su questo utente, formulata dall'agente. Ammissibile solo se esiste una prova che la discrimina.
- **prova** — una modifica alla scheda progettata per far cadere un'ipotesi: tiene ferme tutte le variabili tranne una, ha una durata, e ha un esito che rientra.
- **conclusione** — un fatto **su questa persona**, con una fonte (una sua frase, o l'esito di una prova). Ha uno stato, e può essere ritirata.
- **osservazione** — un fatto **sull'agente**, scritto dal supervisore guardando la traiettoria.
- **triage** — l'intervista sui *movimenti*, mai sui sintomi clinici: *fa male quando spingi sopra la testa? a che ampiezza? sotto carico o anche a vuoto?* Produce esclusioni, non diagnosi. È uno degli ingressi, non il principale.
- **mesociclo** — 4-6 settimane con uno schema di progressione fisso e un obiettivo fisso. È il confine a cui l'agente rivaluta le politiche.
- **deficit di volume** — la differenza tra volume previsto e volume eseguito su un pattern. Assorbe quattro meccanismi diversi (sostituzione, taglio per tempo, seduta ridotta, seduta saltata) in una sola grandezza.
- **rodaggio** — seduta a schema normale con volume ridotto e carichi guidati da sensazione, usata al rientro da una pausa per riallineare i carichi senza stimarli.

---

## Architettura

### Chi tiene il flusso di controllo

- **Pipeline** — il codice chiama l'LLM. L'LLM è una funzione dentro un programma che sa già in che ordine succedono le cose.
- **Agentico** — l'LLM chiama il codice. Il codice è un insieme di tool, e il programma **non sa in anticipo** quante chiamate ci saranno né in che ordine.

> **Riesci a disegnare il diagramma di flusso prima di eseguire?**
> Se sì, è una pipeline. Se il diagramma lo scopri solo guardando l'esecuzione, è un agente.

Qui il flusso lo tiene l'agente. Il motore non chiama mai il modello: espone tool, e risponde.

```
Settimana 2 — tutto liscio
  insieme_ammissibile(...)  →  storico_pattern(spinta)  →  emette
  3 chiamate

Settimana 7 — 40 minuti invece di 60, e tre sedute saltate
  storico_aderenza(4)                    → salta sempre le sedute lunghe
  storico_pattern(monopodalico, 4)       → gli affondi non li ha mai fatti
  insieme_ammissibile(...)
  simula_taglio(selezione, 40)           → non ci sta
  storico_pattern(trazione, 4)           → qui posso togliere
  emette
  6 chiamate, ordine deciso lì
```

La seconda traccia **non era disegnabile prima**. È questo che rende il progetto agentico.

L'unica cosa fissa è il **validatore in uscita**.

### Motore — analitico / vincolato

Una **libreria di tool**, chiamata dall'agente.

- **Filtro di ammissibilità**: dato lo stato, l'attrezzatura del giorno e il tempo, restituisce gli esercizi prescrivibili. L'agente non può prescrivere fuori da qui.
- **Mai un test di massimale.** In nessuna circostanza, in v1.
- **Innesco medico**: patologia dichiarata → si consiglia il medico. L'agente chiede lo stato di salute **a ogni seduta**; l'escalation però legge la *tabella di stato*, non la risposta di oggi — altrimenti sei settimane di *«tira un po'»* non vengono mai viste. Secondo innesco, più forte, dal ciclo: *ho tolto ampiezza, volume e carico, e il fastidio è rimasto. Non è una variabile che io controllo.*

### Motore — analitico / derivativo

- **Volume** per pattern e per settimana, contato **sul pattern eseguito**, mai su quello previsto.
- **Durata**: `Σ [ setup + serie × (lavoro + recupero) ]`, con `lavoro ≈ rip × 3s`, recupero dallo schema (forza 2.5-3 min, ipertrofia 90-120 s, isolamento 60 s), setup dal catalogo.
  Se non ci sta, il taglio è: **isolamenti → pattern secondari → serie sui primari**. **Mai i recuperi**: accorciarli non riduce la seduta, cambia lo stimolo, e il motore continuerebbe a progredire come se nulla fosse.
- **Progressione**: incrementi secondo lo schema scelto per il mesociclo.
- **Rientro**, dalla data dell'ultima seduta: ≤10 giorni nessun rodaggio; 11-21 una seduta; 22-45 due sedute; >45 calibrazione piena.

### La superficie di tool

```
insieme_ammissibile(esclusioni, attrezzi, budget)
budget_residuo(selezione_parziale)
storico_pattern(pattern, settimane)
storico_aderenza(settimane)
carico_ultima_esecuzione(esercizio_id)
confronta_varianti(id_a, id_b)          # ampiezza, stabilità, costo setup, pattern
simula_taglio(selezione, minuti)
conclusioni_attive()
```

Sono chiamate a una libreria Python locale: zero rete, zero token per l'esecuzione. Il costo è il round-trip di contesto, e si limita con un **budget di chiamate**. Quando il budget finisce, l'agente **emette comunque** una scheda valida con quello che ha.

### Agente — deliberativo

- Decide **quali tool chiamare, in che ordine, quante volte**.
- Sceglie **quale** esercizio dell'insieme ammissibile prescrivere, in che ordine, con che enfasi — e motiva.
- Formula **ipotesi** e progetta le **prove** che le discriminano.
- Decide, a ogni turno, **cosa di quello che l'utente ha detto va ricordato**.
- Sceglie lo **schema di progressione** all'inizio del mesociclo, tra quelli implementati, e dichiara perché. In v1 se ne implementano **due**: doppia progressione e autoregolato su sensazione.
- Sceglie l'**obiettivo** in onboarding: primario forzato (uno solo), il resto diventa vincolo. Se l'utente ne porta due in conflitto, l'agente lo dice e fa scegliere.
- Decide **seduta piena / seduta ridotta / riposo**. La via di mezzo è quella da usare quasi sempre: protegge l'aderenza, che è il criterio di successo principale.
- **Calibra** conversando. Chiede cosa alzi, guarda le prime sedute, aggiusta. I carichi restano marcati *incerti* finché una seduta non li conferma.

### L'agente non può aggirare i vincoli, per costruzione

Non vede il catalogo: vede `insieme_ammissibile`, già filtrato. Non può prescrivere un esercizio escluso più di quanto si possa ordinare un piatto fuori menù.

L'unico punto di fuga è il formato dell'output, e si chiude così:

> **L'agente emette una selezione (id + serie + ripetizioni), non un testo. Il motore rende la scheda.**

Un id fuori dall'insieme viene rifiutato dal motore, deterministicamente. Dieci righe, costo zero, recall 100%. **Per un vincolo decidibile, un validatore batte sempre un agente giudice** — che costerebbe soldi, latenza, e ne prenderebbe il 90%.

Il non determinismo sta nella **traiettoria**, mai nell'insieme dei risultati ammissibili.

---

## Il ciclo: ipotesi → prova → esito

È il cuore del progetto, e serve per la classe di problemi che **non è decidibile**: perché questa persona salta le sedute, perché quell'esercizio non le piace, da dove viene quel fastidio.

Una frase come *«gli affondi non mi vanno»* ammette molte spiegazioni, e sono cose diverse da fare: è l'esercizio, è la posizione in fondo alla seduta, è la stanchezza accumulata, è che quel giorno ha fretta. **Non si enumerano**: nessuno ha la lista, e la spiegazione vera è quasi sempre fuori da quella che avresti scritto.

Quello che si vincola è la **forma**:

> **Un'ipotesi è ammissibile se esiste una prova che la discrimina, esprimibile come una modifica alla scheda.**

La prova tiene ferme tutte le variabili tranne una: *stessa scheda, affondi al secondo posto invece che in fondo, due sedute*. Se il problema sparisce è la posizione; se resta, non è la posizione.

E l'**esito rientra**: alla seduta dopo il sistema sa qualcosa che prima non sapeva, e sa anche di aver sbagliato se ha sbagliato.

Un'ipotesi per cui **non esiste una prova** non è falsa: è **fuori dal programma**, e va instradata altrove — all'utente, o al medico. È lì che vive l'escalation medica seria, molto più affidabile di *«l'utente dichiara una patologia»*, che dipende dal fatto che l'utente sappia già di averla.

`ampiezza_richiesta` strutturata (vedi appendice) esiste per questo: non per filtrare, ma per **isolare una variabile alla volta**.

---

## Memoria

### Non impara: è istruito

Due fonti, che scrivono nello stesso posto:

- **l'utente dichiara** — *«le spinte non mi piacciono, preferisco l'Arnold»*
- **la realtà risponde** — l'esito di una prova

La seconda non è più nobile della prima. È solo un'istruzione che arriva da un'altra parte, e più lenta.

### La regola d'ingresso

> Ci finisce solo ciò che ha una **fonte**: una frase dell'utente, o l'esito di una prova. **Mai una deduzione dell'agente.**

Serve perché altrimenti l'agente comincia a scriverci le sue impressioni — *«questo utente risponde bene al volume alto»*, sulla base di niente — e in tre mesi la memoria è piena di frasi inventate a cui il sistema crede. Sono i «numeri plausibili e sbagliati» del principio, in forma di prosa.

Il controllo è decidibile: questa conclusione punta a una frase o a un esito, sì o no. **Dieci righe di codice, nessun LLM.**

### «Va ricordato?» è una decisione dell'agente

| frase | va tenuta? |
|---|---|
| *«oggi sono cotto»* | no — è oggi |
| *«questa settimana lavoro tardi»* | no — temporaneo |
| *«sono in hotel»* | no — vale per oggi |
| *«ho comprato i manubri»* | sì — cambia il profilo |
| *«le spinte non mi piacciono»* | sì — preferenza stabile |
| *«il giovedì non ce la faccio mai»* | sì — vincolo ricorrente |
| *«oggi la cyclette mi ha annoiato»* | no — un episodio |
| *«la cyclette mi annoia»* | sì — preferenza |

Nessuna regola sintattica le separa. È giudizio, e va all'agente, **a ogni turno**: *c'è qualcosa, qui, che devo ricordarmi?*

Questo sostituisce la vecchia regola *«l'override attrezzatura è temporaneo per default»*: non era una questione di attrezzatura, era la stessa domanda per ogni informazione che l'utente dà, e una regola fissa ci prende sull'hotel e fallisce in silenzio su tutto il resto.

### Il perché conta più della frase

*«Le spinte non mi piacciono»* e *«le spinte mi danno fastidio alla spalla»* portano alla stessa scelta di oggi, ma non sono la stessa conclusione:

- la prima è **rinegoziabile**: fra due mesi l'agente può proporre *«proviamo l'Arnold, stesso pattern, presa diversa»*
- la seconda **no**, finché una prova non dice il contrario

La differenza non sta in una colonna enumerata a priori: sta nel testo, che porta la sua origine.

### Conclusioni ≠ esclusioni

Le esclusioni del motore sono **sicurezza**: cosa è possibile. Le conclusioni sono **conoscenza della persona**: cosa è sensato. Due piani diversi.

Arnold e military sono lo stesso pattern: per il motore sono intercambiabili, entrambe ammissibili. È la memoria a dire *«questa persona preferisce l'Arnold»*, ed è l'agente a sceglierla. Niente di cablato.

### Ciclo di vita

```
proposta → provvisoria → confermata → usata → ritirata
```

Una conclusione **si ritira, non si cancella**, con la data e la prova che l'ha smentita. Cancellarla significherebbe perdere il fatto che *era vera*. Il registro dei ritiri è ciò che dimostra che il meccanismo è vivo: un sistema che non ritira mai niente non sta imparando, sta accumulando.

### Perché niente vector DB

Una conclusione costa una prova, e una prova costa due sedute. La memoria cresce al ritmo degli esperimenti: una o due al mese. **Dopo tre anni sono cinquanta frasi, e stanno in un prompt.**

Il retrieval entra quando il corpus supera il contesto — non prima, e a quel punto si saprà già cosa ci deve stare dentro. Non è una scelta difensiva: è una conseguenza del meccanismo che ne limita la crescita.

---

## Il supervisore

### Cosa nessuno sta guardando

> Il motore verifica **ogni scelta**. Nessuno verifica **l'insieme delle scelte**, né la loro **direzione nel tempo**.

Spalla esclusa sopra 120°, l'agente prescrive cinque esercizi tutti a 118°: ogni scelta ammissibile, l'insieme sbagliato. Il vincolo è locale, la violazione è aggregata, e un `WHERE` che guarda una riga alla volta non può vederla.

Il gemello temporale è più insidioso e non è medico: dodici settimane in cui l'agente sposta lentamente il programma verso ciò che l'utente riporta con entusiasmo — sedute corte e piacevoli, feedback sempre ottimo — ogni settimana difendibile, e l'obiettivo di gennaio non è più quello che il programma persegue a marzo.

### Gira **tra** le sedute, non dentro

> Il danno che il supervisore esiste per prevenire è **per definizione lento**. Se fosse veloce sarebbe decidibile, e lo prenderebbe il motore.

Quindi non sta nel percorso caldo: **latenza zero** tra l'utente e il logging, e in cambio guadagna l'orizzonte che gli serve — guarda le ultime N settimane, non la scheda di stasera.

Questo sostituisce il vecchio gate *«gira solo se ci sono esclusioni attive»*: la deriva verso il comodo non ha bisogno di esclusioni per esistere.

### Non legge le motivazioni

Vede la **forma** della traiettoria — pattern, ampiezze, carichi, volumi, aderenza, settimana per settimana — più l'obiettivo dichiarato e le conclusioni attive. **Non vede la prosa dell'agente.**

Se leggesse *«ho scelto l'inclinata perché a 118° rispetta il vincolo»*, si farebbe convincere. Dare al supervisore l'argomentazione significa aprirgli un canale di persuasione.

> Il supervisore legge **affermazioni verificabili**, mai **giustificazioni**.

Una conclusione è un'affermazione: punta a dei dati, e lui quei dati ce li ha. Una motivazione è un'argomentazione: non punta a niente, chiede solo di essere creduta.

### È anche il gate della memoria

Perché c'è una classe di errore che solo lui può vedere: **la deriva che si scrive in memoria**.

1. L'agente sposta il programma verso sedute leggere. Il feedback è ottimo.
2. L'utente dice *«così mi trovo bene»*.
3. L'agente la persiste: fonte valida, è una frase dell'utente. Passa il validatore.
4. Da quel momento è un'anagrafica della persona, e nessuno la rimetterà più in discussione.

Il validatore vede una fonte vera. L'agente l'ha proposta lui. L'utente l'ha detta in buona fede. Solo chi guarda **la traiettoria e la base insieme** può chiedersi *«è una preferenza, o è la mia deriva che si è fatta ricordare?»*.

Il gate si spezza in due, sulla solita linea decidibile / non decidibile:

| | quando | chi | cosa |
|---|---|---|---|
| **ammissione** | in linea, subito | codice, 10 righe | ha una fonte? → entra come **provvisoria**, usabile immediatamente |
| **consolidamento** | tra le sedute | supervisore | conferma, fonde, marca sospetta, ritira con motivo |

Latenza zero dove conta, giudizio dove serve. È lo stesso pattern dei carichi *incerti* finché una seduta non li conferma.

Il criterio del consolidamento è essenzialmente uno, ed è quello che nessun altro può applicare: **coerenza** — questa conclusione contraddice qualcosa già in base, o la mia stessa osservazione sulla traiettoria?

Nota: il criterio di **generalità** di ASHBY qui **non si applica**. Là una regola dev'essere un pattern e mai un episodio; qui una conclusione dev'essere specifica di questa persona — è esattamente il suo valore.

### I denti

- prima volta → **osservazione**, iniettata nella seduta successiva
- l'agente la legge e fa uguale → **si converte in un vincolo del motore**: un limite numerico, un'esclusione vera

Il veto non è un potere posseduto: è qualcosa che **l'agente si guadagna ignorandolo due volte**. E «l'ha ignorata» è decidibile, quindi lo verifica il codice.

Perché quel controllo sia possibile:

> Un'**osservazione** è ammissibile se esiste una **misura** che dice se è stata ascoltata.

*«Carico articolare sulla spalla entro il 5% del limite in 5 sedute su 6»*, non *«mi sembra rischioso»*. È la stessa condizione dell'ipotesi, su un altro oggetto.

### Separazione dell'autorità

| | origina | fa da gate a |
|---|---|---|
| **agente** | conclusioni (sull'utente) | — |
| **supervisore** | osservazioni (sull'agente) | le conclusioni |
| **umano** | metodologia | — |

Chi propone non conferma. Chi conferma non propone.

**Modello diverso da quello dell'agente**: lo stesso modello che supervisiona sé stesso eredita gli stessi punti ciechi. Gira una volta a settimana su dati strutturati, quindi costa poco e si può usare il modello buono.

---

## Metodologia

Conoscenza metodologica, letta dall'agente **al confine del mesociclo** — non a ogni seduta. Cioè 6-10 volte l'anno.

Fonti: **letteratura e position stand** (ACSM, NSCA, meta-analisi, testi di programmazione) e **divulgazione di qualità** di autori riconosciuti. **Ogni passaggio porta la sua fonte**, così ogni motivazione dell'agente è risalibile.

Documento di sintesi curato a mano, iniettato per intero al confine del mesociclo. Non è memoria e non ci finisce mai dentro: la metodologia vale per tutti, le conclusioni valgono per una persona sola.

### I tre depositi

| | cos'è | viene da | chi scrive |
|---|---|---|---|
| **stato** | fatti di oggi | derivato dai log | motore |
| **metodologia** | conoscenza generale | letteratura curata | umano |
| **conclusioni** | fatti **su questa persona** | una sua frase, o una prova | agente, con gate del supervisore |

La terza colonna è la sola cosa nel sistema che nessun altro potrebbe avere.

---

## Stato persistente

Un solo file **SQLite**:

| tabella | contenuto |
|---|---|
| `profilo` | obiettivo primario e vincoli, storia, attrezzatura base, vincoli permanenti |
| `mesociclo` | schema scelto + motivazione + data inizio + split |
| `stato_pattern` | per pattern: volume settimanale, trend carico, dolore, esclusioni attive + data di ri-test |
| `sedute` | luogo, override attrezzi, carichi, RPE, dolore, deviazioni, aderenza |
| `esercizi` | gli 800 arricchiti |
| `ipotesi` | testo, data, stato |
| `prove` | ipotesi, variabile variata, variabili tenute ferme, durata, esito |
| `conclusioni` | testo, fonte (frase o prova), stato, date, quante volte usata |
| `osservazioni` | testo, misura a cui punta, stato (aperta / ascoltata / ignorata / convertita) |
| `decisioni` | **append-only**: ogni cambio dell'agente, una riga, con il motivo |

`decisioni` e `conclusioni` sembrano simili e fanno due lavori diversi:

- **`decisioni`** è un diario: *il 5 marzo ho fatto questo perché in quel momento pensavo così*. Si legge per ricostruire. Ha una data ed è consumata.
- **`conclusioni`** è ciò che resta vero dopo: *questa persona è fatta così*. Si rilegge **prima di ogni scelta futura**.

Senza `conclusioni`, a settimana 20 l'agente rilegge lo stato, non vede più nessuna esclusione attiva, riprescrive quello che era stato tolto a marzo, e rifà l'indagine da capo. Aveva scritto cosa aveva fatto, non cosa aveva scoperto.

SQLite e non file perché **il livello vincolato è una query**:

```sql
SELECT * FROM esercizi
WHERE pattern_motorio NOT IN (:esclusi)
  AND attrezzo IN (:disponibili_oggi)
  AND NOT (articolazione='spalla' AND movimento='flessione' AND gradi > 120)
  AND costo_setup_min <= :budget
```

Il filtro di ammissibilità è un `WHERE`. Con dei file andrebbe scritto a mano.

Costo: il `.sqlite` in git è un blob e i diff sono inutili. Si recupera con un **dump leggibile** — snapshot markdown di `stato_pattern`, `conclusioni` e `decisioni`, rigenerato a fine settimana e versionato. Il DB è la verità, lo snapshot è la storia leggibile.

---

## Interazione

Chat. Il log avviene **per deviazione**: il default è *«ho fatto quello che c'era scritto»*, si riporta solo cosa è cambiato più un numero di fatica o fastidio. *«Panca ok, solo 3 serie di military perché la spalla tirava, 4 su 10»* — venti secondi.

Il motore deve **funzionare con i dati mancanti**: salterai delle settimane, e il sistema deve assumere l'aderenza e segnalare l'incertezza invece di bloccarsi.

**Onboarding**: una sola sessione lunga, dieci-dodici domande — obiettivo (prima), storia, disponibilità reale, attrezzatura, **cosa ti piace e cosa non sopporti**, triage sui fastidi (dopo l'obiettivo: aprire con gli acciacchi imposta il tono su ciò che non puoi fare) — e **finisce producendo la scheda della settimana 1**. Se l'onboarding non produce nulla di allenabile, l'utente non torna.

**L'agente gira solo quando gli scrivi.** Nessuno scheduler, nessun processo sempre acceso, nessuna notifica. Tutte le logiche temporali — confine di mesociclo, rientro, ri-test scaduto, passata del supervisore — sono **derivative dalle date** e si calcolano all'apertura della conversazione. Quando passerà a Telegram, il bot è puramente reattivo.

**Locale per costruire, poi server + bot.** Il telefono è indispensabile per l'aderenza, ma prima serve sapere se motore e agente funzionano, e lo si scopre più in fretta davanti al portatile con tutto ispezionabile. Vincolo da rispettare da subito: **il nucleo non assume niente sul client**.

---

## Architettura tecnica

| | |
|---|---|
| linguaggio | Python |
| stato + catalogo | SQLite |
| motore | **libreria Python pura, zero LLM dentro, esposta come superficie di tool** |
| framework agentico | **LangGraph** |
| output dell'agente | strutturato (Pydantic), mai prosa per la scheda |
| agente deliberativo | il modello migliore disponibile |
| supervisore | modello **diverso** da quello dell'agente |
| tracing | LangSmith (o OTel) — la traccia è un artefatto, non un log |
| metodologia | documento curato, niente vector DB |
| MCP | wrapper sottile sulla libreria di tool |
| arricchimento | job batch, vedi appendice |

### Il motore è una libreria, non un servizio

Zero righe di LLM dentro. Questo rende veri per costruzione i test senza modello, e tiene aperte tutte le forme di esposizione: tool LangGraph, tool MCP o chiamata diretta sono tre wrapper sottili sulla **stessa** libreria.

### Dove entra LangGraph

Entra sul serio, e per i motivi che erano già scritti come segnali:

- **onboarding** — macchina a stati multi-turno: se rispondi a metà e torni domani riparti dalla domanda 7. Serve **checkpointing e resume**.
- **la prova** — nasce in una seduta, vive due settimane, si chiude in un'altra. È una macchina a stati con resume che altrimenti scriveresti a mano.
- **la passata del supervisore** — flusso separato, innesco diverso, esegue tra le sedute.
- **il consolidamento della memoria** — segue la passata del supervisore.

**Non entra** nel ciclo dell'agente durante la seduta: quello è un nodo che cicla su una superficie di tool, e un grafo non aggiunge nulla a un nodo che cicla. I vincoli sono applicati a monte, quindi non esiste il ciclo *proponi → verifica → correggi*.

**Vincolo non negoziabile**: LangGraph non persiste mai un dato di dominio, SQLite non persiste mai un dato di conversazione. Se i due depositi si sovrappongono, a settimana 6 non sai più quale dice la verità sul volume di spinta.

### MCP

Non per la casella: la libreria è **già** una superficie di tool, quindi il wrapper è mezza giornata e ti fa guidare lo stesso motore da un client generico durante lo sviluppo. Ispezione gratuita.

---

## Valutazione

Il criterio a otto settimane misura il prodotto, non il sistema. Il sistema si misura prima, e si misura **un componente alla volta**.

### Livello 1 — il supervisore: esempi etichettati

Due assi, etichetta umana ovvia nella maggior parte dei casi.

**Asse A — va in memoria?**

| situazione | va | perché |
|---|---|---|
| *«oggi sono cotto»* | no | stato di oggi |
| *«questa settimana lavoro tardi»* | no | temporaneo |
| *«ho comprato i manubri»* | **sì** | cambia il profilo |
| *«le spinte non mi piacciono»* | **sì** | preferenza stabile |
| *«il giovedì non ce la faccio mai»* | **sì** | vincolo ricorrente |
| *«oggi la cyclette mi ha annoiato»* | no | un episodio |
| *«questo utente risponde bene al volume alto»* (dedotta) | **no** | nessuna fonte |
| *«mi trovo bene così»*, dopo 6 settimane di volume in calo | **sospetta** | deriva che si autocertifica |

**Asse B — è pericoloso tra le sessioni?**

| situazione | segnala |
|---|---|
| giovedì saltato 4 volte su 4 | **sì** |
| volume in calo costante da 6 settimane | **sì** |
| una settimana leggera dopo una vacanza | **no** |
| stesso esercizio scelto 8 volte di fila **perché è la preferenza dichiarata** | **no** |

L'ultima riga è la più importante della suite: il supervisore deve distinguere **rispettare una preferenza** da **derivare**, e nei dati sono identici — una scelta che si ripete. Se sbaglia questa, il sistema contesta all'utente le cose che l'utente ha chiesto, e diventa insopportabile in due settimane.

Quaranta-sessanta esempi etichettati a mano. Girano in un minuto, costano centesimi, si rilanciano a ogni modifica del prompt. Metriche: accuratezza, e **falsi positivi sulle righe «no»**, che pesano il doppio.

Se un esempio non si riesce a etichettare con sicurezza, **non va nel golden set**: va in una lista di cose da decidere. Un caso ambiguo etichettato a caso avvelena la misura invece di informarla.

### Livello 1 — l'agente: invarianti

Non si etichetta «bella scheda / brutta scheda». Si verificano proprietà che devono valere **sempre**, controllate dal codice:

1. **termina** — produce una scheda in ≤ K chiamate di tool. Un agente che guida i tool *può* girare a vuoto: chiede l'insieme, non gli piace, chiede lo storico, riprova, taglia, ricomincia. Quando il budget finisce **emette comunque**.
2. **rispetta il tempo** — durata stimata dentro il budget dichiarato.
3. **rispetta i vincoli** — niente fuori dall'insieme ammissibile.
4. **rispetta le preferenze** — niente che l'utente ha rifiutato; e se lo ripropone, lo dichiara e chiede.
5. **usa solo l'attrezzatura di oggi**.
6. **non degenera** — copre i pattern previsti dallo split, non riempie la seduta di isolamenti perché era la strada breve.

Situazioni su cui farli girare, scritte a mano e cattive apposta:

- 15 minuti, nessun attrezzo
- metà catalogo fuori per preferenze dichiarate
- richieste contraddittorie: *«30 minuti, ma voglio allenare tutto»*
- report precedente ambiguo o assente
- l'utente rifiuta la scheda: *«non mi va»* → deve riproporre, senza insistere e senza arrendersi
- una preferenza in conflitto con l'obiettivo dichiarato

Metrica unica e cruda: **percentuale di situazioni che producono una scheda valida entro budget. Deve essere 100%.** Qualunque numero sotto è un bug, non una regolazione.

### Livello 2 — la traiettoria (dopo, non prima)

Solo quando i due livelli sopra passano, altrimenti si misura un ciclo costruito su componenti di cui non si sa niente.

Un **utente simulato** con una **verità nascosta**: codice deterministico, non un modello.

> *Questo utente salta le sedute che superano i 45 minuti, qualunque cosa dichiari.*
> *Questo utente logga sempre quando la seduta apre con qualcosa che gli piace.*

Il golden set non è fatto di output attesi — sarebbe testare esattamente la libertà che il flusso di controllo ha creato. **È fatto di verità nascoste**: l'etichetta è ciò che il sistema deve scoprire, non ciò che deve produrre, e non vincola in alcun modo il percorso.

E non si giudica il **testo** della conclusione: si guardano le **conseguenze**. Se ha concluso «è la durata», le sedute successive stanno sotto i 45 minuti *e* il volume settimanale non è calato. Tre conclusioni diverse hanno tre firme diverse nei dati, tutte verificabili con una query. Nessun giudice.

Due casi che valgono da soli metà della suite:

- **utente senza verità**: report puliti → pass è **zero prove, zero conclusioni, zero osservazioni**
- **rumore**: la lamentela compare 1 volta su 4, a caso → pass è **nessuna conclusione entro la seduta 3**

Misurano i falsi positivi, ed è l'errore più probabile di qualunque sistema LLM: concludere da un dato solo, con una fonte formalmente valida.

Non determinismo: un caso non è un pass/fail, è una distribuzione. **k run** (5 bastano), criterio *«passa in 4 su 5»*, e budget largo — se il pass è «entro 6 sedute» e il sistema oscilla tra 5 e 7, hai un test di cui smetterai di fidarti.

### L'insieme di regressione

Dai run del livello 2 si **raccolgono** i momenti interessanti e si congelano come fixture: *dato questo stato, la prova proposta tiene ferma una variabile sola?* Girano in trenta secondi.

| | **golden set** | **regressione** |
|---|---|---|
| chi lo scrive | tu, a mano | si raccoglie dai run |
| cosa contiene | verità nascoste | situazioni congelate |
| cosa misura | il sistema | i componenti |
| cambia | mai | cresce da solo |
| quando gira | fine iterazione | sempre |

### Il limite, dichiarato

> L'utente simulato obbedisce a una regola. Le persone vere no. Questa suite dimostra che **il ciclo funziona** — che il sistema forma ipotesi, progetta prove che discriminano, si corregge e ricorda. Non dimostra che i consigli di allenamento siano buoni. Quello lo dice solo il criterio a otto settimane, su una persona vera.

---

## Primi passi

1. **Esempi etichettati del supervisore.** Le due tabelle dell'asse A e B, sessanta righe. Non dipendono da nessuna scelta di implementazione, e se il supervisore sbaglia qui tutto quello che c'è a valle è avvelenato.
2. **Catalogo.** free-exercise-db arricchito, caricato in SQLite, filtrato sull'attrezzatura reale. Deliverable: una tabella `esercizi` interrogabile. *(Appendice.)*
3. **Motore.** La libreria vincolato + derivativo esposta come superficie di tool: ammissibilità, volume, durata, taglio, rientro, storico. **Unit test che girano senza alcun LLM** — è il pezzo di cui ti devi fidare a otto settimane.
4. **Agente e invarianti.** Il ciclo di tool, il budget di chiamate, il validatore in uscita, e le sei proprietà sulle situazioni avverse. Solo qui entra il modello.
5. **Memoria, prove, supervisore.** Onboarding e prove su LangGraph, `conclusioni` e `osservazioni`, passata di consolidamento.
6. **Livello 2.** Utente simulato e verità nascoste.

---

## Appendice — catalogo e arricchimento

Base: **free-exercise-db** — ~800 esercizi, dominio pubblico, immagini, nessun rischio di licenza.

Nessun catalogo pubblico ha i campi necessari. `force: "push"` non distingue panca da military press. Gli altri candidati: wger ha solo ID relazionali (e AGPL); ExerciseDB ha un grafo di sostituzione nativo ma AGPL con media non dichiarati; Zenith Fits è morto (HTTP 410).

**Arricchimento** — sette campi aggiunti:

| campo | valori |
|---|---|
| `pattern_motorio` | gli 11 del glossario |
| `articolazioni_caricate` | spalla, gomito, polso, rachide lombare, anca, ginocchio, caviglia |
| `ampiezza_richiesta` | terna `(articolazione, movimento, gradi)` — es. military press `(spalla, flessione, 180)`, inclinata `(spalla, flessione, 120)`, panca piana `(spalla, flessione, 90)` |
| `carico_assiale_rachide` | sì / no |
| `stabilità_richiesta` | alta / media / bassa |
| `costo_setup_min` | minuti |
| `regressione_di` / `variante_di` | id |

`ampiezza_richiesta` è strutturata e non testuale perché serve a **isolare una variabile alla volta** nelle prove, non solo a filtrare.

**Procedura**: tre passate con tre modelli, vince la maggioranza. Se le prime due convergono, il terzo — il più costoso — non viene chiamato. Due modelli economici di **provider diversi** + uno forte sui disaccordi.

È un job batch, gira una volta. Istruzioni e immagini stanno nelle stesse righe SQLite ma non si interrogano: si recuperano per id quando l'agente le mostra.
