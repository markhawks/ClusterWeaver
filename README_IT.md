# ClusterWeaver

[English](README.md) | **Italiano**

<p align="center">
  <img src="docs/assets/ClusterWeaver-Logo.png" alt="ClusterWeaver — Linux HA Cluster Builder" width="560">
</p>

[![Licenza: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

Strumento per la creazione e la gestione del ciclo di vita dei cluster Linux High Availability.

Versione corrente: **0.1.12** (9 ottobre 2026). La cronologia dei rilasci è disponibile in [`CHANGELOG.md`](CHANGELOG.md) e dal collegamento Changelog dell’interfaccia web.

ClusterWeaver è software libero distribuito con licenza [GNU Affero General Public License v3.0](LICENSE). Le versioni modificate offerte agli utenti attraverso una rete devono rendere disponibile il relativo codice sorgente con la stessa licenza. Per contribuire consulta [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).

Questo primo MVP gestisce progetti e nodi cluster RHEL 7, 9 e 10. Memorizza lo stato ricercabile in SQLite, genera una definizione YAML leggibile, versiona i file dei progetti in un repository Git locale e produce script verificabili prima dell’esecuzione. RHEL 8 non è volutamente supportato.

I progetti possono essere assegnati a Project Group identificati da colore, con nome univoco e descrizione facoltativa. Home mostra gruppi e progetti non raggruppati in sezioni inizialmente chiuse con contatori; Project mantiene l’inventario completo ricercabile e ordinabile, includendo Group come colonna e filtro.

Il workflow remoto è suddiviso in due fasi richiudibili. **Pre-Cluster Configuration** (step 00–04) gestisce bootstrap e discovery SSH, configurazione e verifica della rete, `/etc/hosts` e controlli preliminari. Tutte e tre le operazioni dello Step 00 possono essere visualizzate, copiate e aperte a schermo intero; su RHEL 7.9 la rete viene esclusivamente verificata, rilevando NetworkManager o i legacy network-scripts senza apportare modifiche, mentre RHEL 9.8 e 10.2 conservano la configurazione protetta. **Cluster Base Installation and Configuration** installa e verifica i pacchetti Pacemaker (step 05), abilita `pcsd` e autentica i nodi (step 06), quindi crea il cluster con il nome configurato e verifica membership, `WaitForAll` e quorum (step 07). Ogni azione è subordinata al completamento corretto degli step precedenti e registra il risultato per ciascun nodo.

## Requisiti di sviluppo

- RHEL 10.2, ambiente canonico di sviluppo ed esecuzione
- Python 3.12 o superiore
- Git
- `python3-pip`

Su RHEL:

```bash
sudo dnf install git python3-pip
```

## Installazione

Per l’installazione automatica su RHEL utilizza gli script descritti in [`setup/README.md`](setup/README.md). Comprendono installazione iniziale da GitHub, installazione da checkout locale, aggiornamenti sicuri, migrazione del database, servizio systemd, configurazione facoltativa di firewalld e verifica dello stato.

**L’installazione offline è deprecata dalla versione 0.1.12. Questa release non pubblica bundle per l’installazione offline. Le istruzioni seguenti restano come riferimento storico.**

Per server RHEL 10.2 x86_64 senza accesso a Internet, [`setup/offline-container/README.md`](setup/offline-container/README.md) descrive il bundle OCI per Podman. Il server di destinazione usa esclusivamente i pacchetti forniti da Satellite e l’archivio trasferito; durante l’installazione non contatta GitHub, PyPI o registry esterni.

Configurazione manuale dell’ambiente di sviluppo:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Imposta una chiave privata per le sessioni al di fuori del controllo versione:

```bash
export CLUSTERWEAVER_SECRET_KEY='sostituire-con-un-valore-casuale'
export CLUSTERWEAVER_LOGIN_USERNAME='admin'
export CLUSTERWEAVER_LOGIN_PASSWORD='changeme' # solo bootstrap del primo amministratore
```

I valori predefiniti inclusi nel progetto sono adatti esclusivamente allo sviluppo locale.

Al primo avvio, se la tabella utenti è vuota, viene creato l’amministratore `admin` con password `changeme`. Al primo accesso sono consentiti solamente **Configuration**, cambio password e logout fino alla sostituzione di `changeme`; il controllo protegge anche le installazioni esistenti che usano ancora la credenziale originale. Le credenziali di bootstrap vengono ignorate dopo la creazione del primo utente; le password sono memorizzate in SQLite esclusivamente come hash con salt.

## Autenticazione, ruoli e aspetto

ClusterWeaver richiede l’autenticazione per tutte le pagine dei progetti. La pagina Configuration permette di modificare password e tema personali e, agli amministratori, di gestire gli account.

- `user`: accesso in sola lettura a progetti, nodi, script generati e risultati delle esecuzioni.
- `clusteradmin`: può creare e gestire cluster ed eseguire workflow remoti, ma non può creare, modificare o eliminare utenti.
- `administrator`: gestione completa di cluster e utenti.

Per ogni account viene registrata la data dell’ultima modifica della password. Il tema predefinito è grigio scuro; ogni utente può selezionare autonomamente il tema chiaro. Facendo clic sul logo dopo l’accesso vengono mostrate versione di ClusterWeaver, autore, progetto GitHub e versioni dei componenti software.

## Inizializzazione e migrazione del database

```bash
source .venv/bin/activate
alembic upgrade head
```

In produzione i dati SQLite sono memorizzati in `/var/lib/clusterweaver/data`; l’ambiente di sviluppo utilizza `data/clusterweaver.db`. I database sono esclusi da Git e non costituiscono l’unica copia della configurazione dei progetti.

## Avvio del server di sviluppo

```bash
source .venv/bin/activate
python run.py
```

Apri `http://127.0.0.1:5000`. Il server di sviluppo ascolta solamente su localhost e non deve essere utilizzato come modalità di pubblicazione in produzione.

Per renderlo raggiungibile da un altro sistema della stessa rete protetta:

```bash
export CLUSTERWEAVER_HOST=0.0.0.0
python run.py
```

Apri quindi `http://<ip-vm>:5000`. Se firewalld è attivo, occorre autorizzare anche la porta TCP 5000 nella zona della VM. Non esporre direttamente il server Flask di sviluppo su reti pubbliche o non affidabili.

## Servizio systemd

Il servizio installato `clusterweaver-control.service` esegue `/opt/clusterweaver/app` usando il virtual environment `/opt/clusterweaver/venv`. Gunicorn viene eseguito con l’account non privilegiato `clusterweaver`, si avvia al boot, conserva lo stato in `/var/lib/clusterweaver` e legge la configurazione privata da `/etc/clusterweaver/clusterweaver.env`.

Per provare le modifiche del repository locale sul servizio nativo senza ripetere un'installazione completa:

```bash
sudo ./setup/update-local.sh
```

Lo script conserva progetti e configurazione, esegue il backup di SQLite, applica le migrazioni, riavvia e verifica il servizio. Se la verifica fallisce ripristina automaticamente applicazione e database precedenti. Il virtual environment viene ricostruito solamente quando cambia `requirements.txt`.

## Architettura lato sistema operativo

Nell’installazione raccomandata per RHEL 10.2 senza accesso a Internet, ClusterWeaver viene eseguito come container Podman gestito da systemd attraverso Quadlet:

```text
Browser
   │ TCP/5000
   ▼
systemd → Podman → ClusterWeaver (Flask/Gunicorn)
                         │
                         ├── database SQLite
                         ├── progetti YAML e storico Git locale
                         └── SSH TCP/22 → nodi cluster gestiti
```

La struttura sul sistema host è volutamente ridotta:

```text
/etc/clusterweaver/clusterweaver.env             # configurazione e segreti protetti
/etc/containers/systemd/clusterweaver.container  # definizione Podman Quadlet
/var/lib/clusterweaver/data/clusterweaver.db      # database SQLite persistente
/var/lib/clusterweaver/data/projects/             # progetti YAML e storico Git persistenti
```

Il codice applicativo e le dipendenze Python sono contenuti nell’immagine OCI versionata, per esempio `localhost/clusterweaver:0.1.12`. Il container viene eseguito con UID non privilegiato `10001`, usa un filesystem applicativo in sola lettura, non possiede capability Linux, può scrivere solamente nella directory dati montata ed esegue un health check periodico. Sul server isolato Satellite fornisce soltanto i pacchetti RHEL richiesti; il bundle trasferito contiene l’immagine applicativa e non contatta GitHub, PyPI o registry esterni.

Comandi principali:

```bash
systemctl status clusterweaver-control
systemctl start clusterweaver-control
systemctl stop clusterweaver-control
systemctl restart clusterweaver-control
systemctl reload clusterweaver-control
journalctl -u clusterweaver-control -f
```

È disponibile anche lo script di servizio:

```bash
./scripts/clusterweaver-control start
./scripts/clusterweaver-control stop
./scripts/clusterweaver-control restart
./scripts/clusterweaver-control reload
./scripts/clusterweaver-control status
./scripts/clusterweaver-control logs
```

`reload` applica senza interruzioni le modifiche Python e dei template. Per gli asset statici è normalmente sufficiente aggiornare il browser. Dopo modifiche alle dipendenze o all’unità systemd usa `restart`.

## Esecuzione dei test

```bash
source .venv/bin/activate
pytest
```

I test utilizzano database e repository temporanei isolati; non contattano i nodi cluster e non eseguono comandi su di essi.

## Dati di esecuzione

In produzione ogni progetto viene scritto in:

```text
/var/lib/clusterweaver/data/projects/<slug-progetto>/project.yaml
```

I file portabili `.cwp` possono anche essere depositati in `/var/lib/clusterweaver/data/Project-Import` e selezionati da **Projects → Import project → Import from server**. La directory può essere popolata manualmente oppure essere il working tree di un repository Git privato gestito separatamente. ClusterWeaver non conserva credenziali Git e non esegue `git pull`: legge solamente file `.cwp` regolari contenuti direttamente nella directory e applica le normali verifiche di checksum e schema.

Le piccole modifiche applicative possono essere trasferite a un'installazione Podman isolata tramite pacchetti `.cwu` protetti da checksum. L'aggiornamento usa un mount applicativo in sola lettura, salva il database, verifica il servizio e applica il rollback automatico; il bundle OCI completo serve solamente quando cambiano dipendenze o immagine di base. La procedura è descritta in `setup/offline-container/README.md`.

`data/projects/` viene inizializzata come repository Git locale separato. Le modifiche YAML significative producono commit; database SQLite, log e file YAML contenenti segreti sono esclusi. Gli script generati vengono mostrati per la revisione. Le password SSH sono utilizzate solamente in memoria e non vengono scritte nei dati del progetto o nei log.

## Progetti portabili

Ogni progetto può essere esportato dalla tabella Projects come archivio portabile `.cwp` e importato in un’altra istanza ClusterWeaver. L’importazione crea sempre un nuovo progetto con un nuovo UUID e azzera lo stato delle esecuzioni remote. L’archivio contiene la configurazione modificabile, incluso il nome Pacemaker indipendente del cluster, gli script del workflow, i metadati del formato e i checksum SHA-256; esclude password, chiavi SSH, segreti applicativi, log e risultati degli step.

## Variabili di configurazione

- `CLUSTERWEAVER_SECRET_KEY`
- `CLUSTERWEAVER_LOGIN_USERNAME`, bootstrap iniziale dell’amministratore; predefinito `admin`
- `CLUSTERWEAVER_LOGIN_PASSWORD`, bootstrap iniziale; predefinito `changeme`, memorizzato come hash e ignorato dopo la creazione del primo utente
- `CLUSTERWEAVER_DATABASE_URL`
- `CLUSTERWEAVER_PROJECTS_ROOT`
- `CLUSTERWEAVER_HOST`, predefinito `127.0.0.1`
- `CLUSTERWEAVER_PORT`, predefinito `5000`
- `CLUSTERWEAVER_DEBUG`, disabilitato per impostazione predefinita
- `CLUSTERWEAVER_SSH_BOOTSTRAP_PASSWORD`, password root iniziale facoltativa conservata esclusivamente nel file di ambiente protetto del servizio

## Struttura delle directory

```text
clusterweaver/
├── core/          # modelli, validazione, generatori, serializzatori e servizi indipendenti dal framework
├── persistence/   # record e repository SQLAlchemy
├── web/           # applicazione Flask, route, form, template e asset statici
└── cli/           # spazio riservato alla futura CLI
cluster_templates/ # template separati per RHEL 7, 9 e 10
data/              # stato SQLite e definizioni dei progetti versionate con Git
migrations/        # cronologia delle migrazioni Alembic
tests/             # test unitari e di integrazione web
```

L’MVP attualmente non include la configurazione delle risorse Pacemaker, il provisioning dello storage, la creazione dello STONITH, l’integrazione Ansible e il supporto a RHEL 8. Le operazioni SSH remote sono subordinate ai prerequisiti del workflow e richiedono una conferma esplicita quando modificano lo stato dei nodi.

## Step 08a: profili DELL OEM

Il workflow **Cluster STONITH Configuration and Testing** include per ora soltanto **08a**. Definisce un endpoint DELL OpenManage Enterprise (IP o hostname, HTTPS/443) e, per ogni nodo, il nome esatto del profilo OEM e lo userid. Le password vengono richieste per la verifica e non sono conservate in SQLite, YAML, Git o archivi `.cwp`.

**Save profiles** conserva le definizioni; **Save and verify OEM profiles** esegue dal server ClusterWeaver richieste HTTPS GET alle API DeviceService e ProfileService (con fallback TemplateService per versioni precedenti). Il controllo segnala nomi mancanti, differenze di maiuscole/minuscole, associazioni errate o non verificabili e dispositivi disconnessi. Mostra gli stati restituiti da OEM senza interpretarli come prova di funzionamento del fencing. Sono previsti 8 secondi per richiesta e un budget condiviso di 45 secondi. La modifica delle definizioni invalida i risultati 08a precedenti.

Il certificato HTTPS OEM deve essere attendibile per il server ClusterWeaver. Per una CA privata impostare `CLUSTERWEAVER_OEM_CA_FILE` al percorso di un file PEM leggibile dal servizio. La migrazione `0016_stonith_ipmi` va applicata prima di avviare questa versione (`alembic upgrade head`). Lo script Python visualizzabile usa lo stesso adattatore di sola lettura e richiede le password interattivamente. Questo step non crea risorse STONITH e non esegue spegnimenti o riavvii.

Riferimenti API: [profili Dell](https://www.dell.com/support/manuals/en-uk/dell-openmanage-enterprise/ome_p_38_api_guide/profiles?guid=guid-044ccf90-224f-4efa-9d91-43c91178eb0d&lang=en-us), [autenticazione Dell](https://www.dell.com/support/manuals/en-us/dell-openmanage-enterprise/ome_p_3.10_api_guide/authentication?guid=guid-12bfee52-90ef-4ef0-b37c-f7071363fb11).

La scelta **DELL iDRAC / IPMI diretto** mostra per ogni nodo hostname, IP o nome iDRAC, nome della futura risorsa STONITH, userid e password. Usa `fence_ipmilan` con LANPlus e `action=status`, dal server ClusterWeaver: installare lì il pacchetto RHEL `fence-agents-ipmilan` (anche nell’immagine se si usa il container). Il controllo legge ON/OFF, con timeout di 20 secondi per nodo e budget totale di 45 secondi; non verifica l’associazione fisica iDRAC/nodo e non esegue fencing. Le password non vengono salvate. Le configurazioni OEM esistenti mantengono la loro modalità dopo la migrazione.

In 08a, **Check fence agents on cluster nodes** è un controllo SSH separato dal test OEM/iDRAC. Salvare prima i profili, poi inserire la password root SSH (o usare quella configurata sul server). Su ogni IP SSH dei nodi elenca i pacchetti `fence-agents*` e gli eseguibili `fence_*`; per IPMI controlla `fence_ipmilan` e legge i metadati con timeout di 10 secondi. Il comando remoto ha limite di 20 secondi e l’intero controllo un budget di 45 secondi. OEM esegue solo l’inventario, non avendo ancora un agente STONITH selezionato. Gli esiti sono conservati separatamente dai test OEM/iDRAC e invalidati quando cambiano i profili o l’identità/IP SSH del nodo.

Per agenti mancanti viene proposto `dnf install fence-agents-all`, da eseguire come root sui nodi interessati con repository RHEL High Availability disponibile tramite Satellite/subscription. Il controllo non installa pacchetti automaticamente. Se l’agente specifico è funzionante, l’assenza del metapacchetto `fence-agents-all` non causa un errore. Gli errori SSH vengono distinti dagli agenti mancanti.

## Accesso SSH persistente per progetto

Nel dettaglio del progetto, nello step 00, **ClusterWeaver SSH key** apre la gestione della chiave dedicata. Il servizio locale continua a girare come utente `clusterweaver` (UID 10001 nel container), mentre i comandi sui nodi vengono eseguiti come root. Non serve usare l’utente root del server applicativo.

Per riprendere un progetto esistente:

1. Impostare gli IP SSH dei nodi. Aprire **ClusterWeaver SSH key** e indicare l’IP sorgente del server visto dai nodi, includendo eventuale NAT. È possibile precompilarlo con `CLUSTERWEAVER_SSH_SOURCE_IP`.
2. Inserire la password root corrente comune o una password diversa per ogni nodo; confermare e scegliere **Install / resume and verify project key**.
3. ClusterWeaver genera una chiave RSA da 3072 bit, aggiunge la pubblica senza rimuovere le chiavi esistenti, registra l’identità SSH del nodo e verifica un nuovo accesso usando esclusivamente la chiave. La chiave diventa attiva quando tutti i nodi correnti superano la verifica. In caso di errore parziale, correggere il nodo e riprendere la stessa installazione.
4. Lasciare vuota la password degli step successivi: discovery, peer trust, rete, step 01–07 e inventario fence 08a usano la chiave attiva, anche se esiste una password predefinita vecchia. Una password inserita esplicitamente richiede invece un accesso temporaneo tramite password. Nessun fallback automatico avviene dopo un errore della chiave.

La rotazione giornaliera della password root non modifica la chiave pubblica autorizzata, purché le policy SSH/PAM continuino a consentire l’accesso. Le password iDRAC/OEM e hacluster restano credenziali distinte. Lo scambio di chiavi tra nodi (00b) resta separato dall’accesso del server ClusterWeaver. Non serve ripetere gli step già completati solo per installare la chiave del server.

Le chiavi sono associate all’UUID del progetto e conservate in `<parent di PROJECTS_ROOT>/ssh_keys/<UUID>/`, per l’installazione standard `/var/lib/clusterweaver/data/ssh_keys/<UUID>/`. `CLUSTERWEAVER_SSH_KEYS_ROOT` consente un percorso alternativo fuori dalla directory Git dei progetti; nel container deve appartenere a un volume persistente leggibile/scrivibile dall’UID 10001. Directory 0700, file privati e `known_hosts` 0600, proprietario il servizio. Le chiavi sono escluse da YAML, Git e `.cwp`; l’importazione crea un nuovo UUID e richiede un nuovo bootstrap. Conservare separatamente un backup protetto della directory delle chiavi: il solo backup SQLite non consente di recuperarle. La cancellazione di un progetto non revoca automaticamente le chiavi sui suoi ex nodi.

Ogni pubblica viene autorizzata con `from="IP",restrict`. I comandi root senza terminale restano consentiti. L’identità del server SSH viene registrata durante l’installazione tramite password; gli accessi successivi rifiutano identità sconosciute o cambiate. Verificare manualmente i fingerprint prima di aggiornare `known_hosts` per nodi reinstallati. Se 00c cambia l’IP di gestione, la nuova connessione deve presentare la stessa chiave host del nodo originale prima di disarmare il rollback.

**Verify key-only access** è di sola lettura. **Rotate project key** mantiene la vecchia chiave attiva finché la nuova non è verificata su tutti i nodi. **Revoke previous key** elimina soltanto la vecchia pubblica usando la nuova chiave attiva e rimuove la privata precedente dal server solo dopo esito positivo su tutti i nodi correnti; nodi rimossi dall’inventario richiedono revoca manuale. Non si avvia un’altra rotazione finché esiste una chiave precedente da revocare. Le operazioni hanno un budget di 90 secondi, con comandi SSH limitati a 20 secondi e risultati per nodo; una scadenza può lasciare un aggiornamento parziale della pubblica, da riprendere. Questa funzionalità non richiede nuove migrazioni database.

## Cluster Operations and Status

Nel dettaglio del progetto, **Gestisci cluster** apre la nuova sezione espandibile dopo i workflow di configurazione e STONITH. Mostra quorum, nodi online, ultimo aggiornamento, servizi Pacemaker/Corosync e abilitazione al boot per nodo, risorse e fallimenti, comando e storico con utente/data/esiti. I controlli richiedono una chiave di progetto attiva e una verifica 00k positiva su tutti i nodi correnti; non richiedono il completamento dei vecchi workflow di installazione.

**Aggiorna stato** esegue controlli di sola lettura via IP SSH, leggendo Corosync, systemd, `crm_mon` XML e `pcs status --full`. Anche gli utenti in sola lettura possono aggiornare e consultare lo stato. Le modifiche richiedono ruolo administrator/clusteradmin e conferma esplicita nella finestra con cluster, nodi, conseguenza, comando e script protetto.

**Avvia/Arresta cluster** eseguono `pcs cluster start/stop` localmente su ogni nodo via SSH, senza dipendere dai nomi per raggiungere i peer; lo stop non usa `--force`. **Abilita/Disabilita al boot** eseguono `pcs cluster enable/disable` e non cambiano lo stato di esecuzione. **Standby/Unstandby** usano il nodename Pacemaker e vengono inviati una sola volta da un coordinatore con quorum. Lo standby dell’ultimo nodo disponibile, senza quorum o in presenza di fallimenti non risolti viene bloccato; il risultato attende anche lo svuotamento delle risorse del nodo. Unstandby non forza il ritorno delle risorse.

Prima di ogni modifica vengono verificati via chiave tutti gli IP SSH, il nome cluster e i nodename esatti nella configurazione e nello stato attivo. Qualunque errore del preflight impedisce l’invio dei comandi di modifica. Le operazioni già conformi vengono verificate senza ripetere il comando. PASS indica l’esito dell’operazione o della raccolta stato, non certifica la salute di tutte le risorse.

I job vengono eseguiti in background nel processo web; HTTP restituisce subito e l’interfaccia legge l’avanzamento ogni 2 secondi. SQLite conserva lo storico e una prenotazione univoca impedisce due job simultanei sullo stesso progetto, anche tra worker. Durante un job sono bloccate modifiche a inventario/chiavi e workflow concorrenti che modificano i nodi. Comandi di modifica: 120 secondi, verifica start/stop: 180 secondi, altre verifiche: 60 secondi, budget totale: 360 secondi; le scadenze vengono ridotte se necessario al budget residuo.

Un timeout di comando o perdita della connessione dopo l’invio produce **UNKNOWN / da verificare**, seguito da lettura dello stato senza ripetere la modifica. Serve un aggiornamento stato positivo prima di un’altra modifica. Un riavvio del worker interrompe il job: dopo 600 secondi la prenotazione viene liberata e l’esito marcato UNKNOWN, senza riavvio automatico del comando. Lo storico non viene incluso nelle esportazioni dei progetti. Applicare la migrazione `0017_cluster_operations` con `alembic upgrade head` prima di avviare questa versione.
