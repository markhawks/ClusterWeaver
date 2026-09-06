# ClusterWeaver

[English](README.md) | **Italiano**

<p align="center">
  <img src="docs/assets/ClusterWeaver-Logo.png" alt="ClusterWeaver — Linux HA Cluster Builder" width="560">
</p>

[![Licenza: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

Strumento per la creazione e la gestione del ciclo di vita dei cluster Linux High Availability.

Versione corrente: **0.1.6**. La cronologia dei rilasci è disponibile in [`CHANGELOG.md`](CHANGELOG.md) e dal collegamento Changelog dell’interfaccia web.

ClusterWeaver è software libero distribuito con licenza [GNU Affero General Public License v3.0](LICENSE). Le versioni modificate offerte agli utenti attraverso una rete devono rendere disponibile il relativo codice sorgente con la stessa licenza. Per contribuire consulta [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).

Questo primo MVP gestisce progetti e nodi cluster RHEL 7, 9 e 10. Memorizza lo stato ricercabile in SQLite, genera una definizione YAML leggibile, versiona i file dei progetti in un repository Git locale e produce script verificabili prima dell’esecuzione. RHEL 8 non è volutamente supportato.

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

Al primo avvio, se la tabella utenti è vuota, viene creato l’amministratore `admin` con password `changeme`. Cambia immediatamente la password dalla pagina **Configuration**. Le credenziali di bootstrap vengono ignorate dopo la creazione del primo utente; le password sono memorizzate in SQLite esclusivamente come hash con salt.

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

`data/projects/` viene inizializzata come repository Git locale separato. Le modifiche YAML significative producono commit; database SQLite, log e file YAML contenenti segreti sono esclusi. Gli script generati vengono mostrati per la revisione. Le password SSH sono utilizzate solamente in memoria e non vengono scritte nei dati del progetto o nei log.

## Progetti portabili

Ogni progetto può essere esportato dalla tabella Projects come archivio portabile `.cwp` e importato in un’altra istanza ClusterWeaver. L’importazione crea sempre un nuovo progetto con un nuovo UUID e azzera lo stato delle esecuzioni remote. L’archivio contiene configurazione modificabile, script del workflow, metadati del formato e checksum SHA-256; esclude password, chiavi SSH, segreti applicativi, log e risultati degli step.

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
