# ClusterWeaver

[English](README.md) | **Italiano**

<p align="center">
  <img src="docs/assets/ClusterWeaver-Logo.png" alt="ClusterWeaver — Linux HA Cluster Builder" width="560">
</p>

[![Licenza: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

Strumento per la creazione e la gestione del ciclo di vita dei cluster Linux High Availability.

Versione corrente: **0.1.11**. La cronologia dei rilasci è disponibile in [`CHANGELOG.md`](CHANGELOG.md) e dal collegamento Changelog dell’interfaccia web.

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

Il codice applicativo e le dipendenze Python sono contenuti nell’immagine OCI versionata, per esempio `localhost/clusterweaver:0.1.11`. Il container viene eseguito con UID non privilegiato `10001`, usa un filesystem applicativo in sola lettura, non possiede capability Linux, può scrivere solamente nella directory dati montata ed esegue un health check periodico. Sul server isolato Satellite fornisce soltanto i pacchetti RHEL richiesti; il bundle trasferito contiene l’immagine applicativa e non contatta GitHub, PyPI o registry esterni.

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
