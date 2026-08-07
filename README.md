# whisper-toolkit

CLI Python de transcription audio **locale**, basé sur Whisper.

> **Statut : en cours de développement.** Transcription locale, diarisation,
> traitement par lot, transcription depuis une URL YouTube et résumé via l'API
> Claude sont implémentés et exécutés pour de vrai, derrière un CLI unifié —
> doublé d'une interface web Streamlit qui appelle le même code.
> Deux réserves : la séparation des locuteurs n'a été testée que sur des voix de
> synthèse, sans chevauchement de parole, et le résumé n'a été mesuré que sur
> une transcription écrite à la main, pas sur une vraie sortie Whisper longue.
> La surveillance de dossier n'est pas commencée.
> Détail dans [Testing Status](#testing-status).

## Usage

Tout passe par une seule commande, avec une sous-commande par mode d'entrée.

```bash
source venv/bin/activate

python src/cli.py transcribe cours.m4a              # un fichier
python src/cli.py batch mes-cours/                  # un dossier entier
python src/cli.py youtube 'https://youtu.be/...'    # une URL YouTube
python src/cli.py summarize output/cours.txt        # résumer un texte déjà produit
```

Les trois premières écrivent dans `output/`. `python src/cli.py --help`, et
`python src/cli.py <sous-commande> --help`, listent le reste.

### Interface web

Une interface Streamlit couvre les trois entrées audio, **en plus** du CLI —
elle ne le remplace pas, et les deux appellent exactement le même code.

```bash
source venv/bin/activate
streamlit run app.py           # http://localhost:8501
```

Trois onglets — *Fichier unique* (glisser-déposer), *Dossier (batch)* et
*YouTube* — avec les mêmes options qu'en ligne de commande, les mêmes sorties
dans `output/`, et un bouton de téléchargement du `.txt`. Ce que l'app n'expose
pas : la sous-commande `summarize` seule (le résumé s'y coche à la volée),
`--summary-model` et `--summary-style`. Détail dans
[`app.py` — interface web](#apppy--interface-web-présentation-seule).

> ⚠️ **Streamlit écoute sur toutes les interfaces par défaut**, pas seulement
> sur `localhost` : lancé tel quel, il affiche une « Network URL » joignable par
> tout le réseau local. Sur un réseau qui n'est pas le tien :
>
> ```bash
> streamlit run app.py --server.address localhost
> ```

### Options

| Option | `transcribe` | `batch` | `youtube` | Effet |
|---|:---:|:---:|:---:|---|
| `--diarize` | ✅ | ✅ | ✅ | identifier les locuteurs (whisperx) au lieu d'une simple transcription |
| `--num-speakers N` | ✅ | ✅ | ✅ | nombre exact de locuteurs, si connu (avec `--diarize`) |
| `--language fr` | ✅ | ✅ | ✅ | forcer la langue — par défaut elle est **détectée**, et la forcer à tort produit une traduction silencieuse (voir [Langue](#langue--détectée-jamais-forcée-par-défaut)) |
| `--summarize` | ✅ | ✅ | ✅ | enchaîner un résumé via l'API Claude — **seule option payante** |
| `--summary-model`, `--summary-style` | ✅ | ✅ | ✅ | modèle et style du résumé enchaîné |
| `--force` | — | ✅ | — | retraiter ce qui existe déjà, résumés compris |

La sous-commande `summarize` prend `--model` et `--style` (mêmes valeurs, sans
le préfixe : elle ne fait que ça).

```bash
# transcription + locuteurs + résumé, en une seule commande
python src/cli.py transcribe reunion.wav --diarize --num-speakers 3 --summarize

# un dossier entier, résumé de chaque fichier, en reprenant là où on s'était arrêté
python src/cli.py batch mes-cours/ --summarize

# résumé sur mesure d'une transcription déjà produite
python src/cli.py summarize output/cours.txt --style "en trois puces"
```

Code de sortie `0` si tout s'est bien passé, `1` sinon — y compris quand un seul
fichier d'un lot a échoué.

### Pourquoi `python src/cli.py` et pas une commande `whisper-toolkit` installée

Le CLI aurait pu être exposé comme un exécutable (`pip install -e .` plus un
`entry_point` dans un `pyproject.toml`), pour taper `whisper-toolkit transcribe
cours.m4a`. Ce n'est **pas** fait, pour trois raisons :

- **Les modules de `src/` s'importent à plat** (`from transcribe import …`), ce
  qui fonctionne parce que `python src/cli.py` place `src/` en tête de
  `sys.path`. Un paquet installable demanderait soit de convertir les six
  fichiers en imports de paquet — un refactor de code qui marche, pour zéro gain
  fonctionnel — soit de publier `transcribe`, `batch`, `summarize` et `youtube`
  comme modules **de premier niveau** dans le `site-packages` du venv. Ces noms
  sont trop génériques pour ne pas entrer en collision un jour.
- **Le gain se limite à quelques caractères.** Le venv doit être activé dans les
  deux cas : une commande installée ne dispense pas de `source venv/bin/activate`.
- **`output/` est relatif au répertoire courant.** Une commande installée invite
  à lancer le toolkit depuis n'importe où, et donc à éparpiller les
  transcriptions dans autant de dossiers `output/` que de répertoires de
  travail. Aujourd'hui la convention est simple : on lance depuis la racine du
  dépôt.

Pour raccourcir la ligne sans rien installer, un alias suffit :

```bash
alias wt="$PWD/venv/bin/python $PWD/src/cli.py"
```

La question se reposera si le toolkit doit être distribué à quelqu'un d'autre.
Ce sera alors un vrai paquet (`whisper_toolkit/` avec des imports de paquet),
pas un `entry_point` posé par-dessus la structure actuelle.

## Fonctionnalités prévues

- **Transcription locale** via [`mlx-whisper`](https://github.com/ml-explore/mlx-examples) (optimisé Apple Silicon)
- **Diarisation** (identification des locuteurs) via [`whisperx`](https://github.com/m-bain/whisperX)
- **Batch** : traitement d'un dossier entier
- **Surveillance de dossier** : transcription automatique des nouveaux fichiers
- **YouTube** : transcription directe depuis une URL via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- **Résumé automatique** de la transcription via l'API Claude
- Le tout dans un **CLI unifié** (`argparse`), doublé d'une **interface web**
  (Streamlit) qui appelle exactement le même code

## Structure

```
whisper-toolkit/
├── CLAUDE.md          # guidelines de dev + contexte projet
├── README.md
├── app.py             # interface web Streamlit (présentation seule)
├── requirements.txt
├── .gitignore
├── .env               # HF_TOKEN pour la diarisation (non versionné)
├── .nltk_data/        # cache NLTK local au projet (non versionné, régénérable)
├── venv/              # environnement virtuel (non versionné)
├── test-audio/        # échantillons de test (ignoré, sauf la fixture synthétique)
├── output/            # transcriptions produites (non versionné)
├── src/
│   ├── cli.py         # CLI unifié — point d'entrée, orchestration seule
│   ├── transcribe.py  # transcription simple (mlx-whisper)
│   ├── diarize.py     # transcription + locuteurs (whisperx)
│   ├── batch.py       # traitement d'un dossier entier
│   ├── youtube.py     # transcription depuis une URL (yt-dlp)
│   └── summarize.py   # résumé d'une transcription (API Claude)
└── tests/             # tests (vide pour l'instant)
```

## Architecture

Le projet a **deux pipelines audio distincts**, qui ne partagent ni backend ni
modèle. Ce n'est pas un accident : chacun est le meilleur outil pour son usage.

| | `transcribe.py` | `diarize.py` |
|---|---|---|
| Backend | `mlx-whisper` | `whisperx` → `faster-whisper` |
| Runtime | MLX | CTranslate2 |
| Matériel | **GPU Metal** (Apple Silicon) | **CPU uniquement** |
| Modèle par défaut | `mlx-community/whisper-large-v3-mlx` | `large-v3` (CTranslate2) |
| Sortie | texte brut | segments `{start, end, text, speaker}` |
| Identifiants requis | aucun | token Hugging Face |

**Pourquoi deux backends.** CTranslate2, sur lequel repose whisperx, n'a pas de
support Metal ni MPS : le chemin diarisation tourne donc entièrement sur CPU,
sans l'accélération dont bénéficie `transcribe.py`. À l'inverse, mlx-whisper
n'offre ni alignement au mot ni diarisation. Utilise `transcribe.py` quand tu
veux juste le texte, vite ; `diarize.py` quand il faut savoir qui parle.

Les deux modules sont indépendants : ni import croisé, ni état partagé.
`diarize.py` refait sa propre transcription plutôt que de réutiliser celle de
`transcribe.py`, car l'alignement au mot exige les sorties internes de
faster-whisper.

### Langue : détectée, jamais forcée par défaut

`transcribe_file()` prend `language: str | None = None` : Whisper détecte la
langue. Les trois CLI exposent `--language` pour la forcer (`fr`, `en`, …), sans
effet en diarisation où whisperx détecte de son côté, fichier par fichier.

**Forcer une langue ne produit jamais d'erreur — ça produit une traduction.**
Whisper à qui on impose une langue qui n'est pas celle de l'audio rend un texte
dans la langue demandée, fluide et plausible, sans le moindre signal. Rien dans
la sortie ne distingue une transcription d'une traduction inventée. C'est le
défaut qu'a révélé la première vidéo YouTube anglaise, transcrite en français ;
la fixture française avec `--language en` le reproduit à l'identique en sens
inverse (voir Test 8).

Un défaut codé en dur à `fr` n'était donc pas tenable pour un toolkit qui avale
des URL YouTube et des dossiers hétérogènes. Et il ne coûte rien de l'enlever :
**texte strictement identique** sur les 5 fixtures françaises, pour un surcoût
**fixe** d'environ 0,3 s — une passe sur la première fenêtre, pas
proportionnelle à la durée (0,5 % sur un fichier de 76 s).

### `cli.py` — une commande, quatre sous-commandes

`cli.py` est une couche d'orchestration au même titre que `batch.py` : il ne
contient **aucune** logique de transcription, de diarisation, de téléchargement
ni de résumé. Chaque sous-commande appelle les fonctions des modules qui la
portent, puis affiche ce qu'elles ont écrit.

```
transcribe FICHIER ──> transcribe_file() | diarize_file()  ──> output/{nom}[_diarized].txt ─┐
batch DOSSIER      ──> process_folder()      (délègue fichier par fichier)                  ├─> --summarize
youtube URL        ──> transcribe_youtube()  (yt-dlp puis délégation)                       ─┘      │
                                                                                                   ▼
summarize FICHIER.txt ─────────────────────> summarize_text()  ──────────────> output/{nom}_summary.txt
```

**`argparse` avec des sous-parseurs, pas de nouvelle dépendance.** Quatre
sous-commandes et une dizaine d'options : `click` ou `typer` n'apporteraient
ici qu'un peu de sucre syntaxique, contre une dépendance de plus à installer et
à suivre. Les options communes aux trois entrées audio sont d'ailleurs
déclarées **une seule fois**, dans un parseur parent (`parents=[audio]`) — il
n'y a donc pas non plus la duplication à laquelle `click` remédierait.

**Les modules frères sont importés dans les fonctions, pas en tête de fichier.**
Importer `youtube` tire yt-dlp, et `diarize`/`batch` tirent nltk : **0,72 s
payées à chaque lancement**, y compris pour un `--help` ou un résumé qui n'en
ont que faire. Avec les imports paresseux, `--help` répond en **0,03 s**. C'est
le même raisonnement que pour `mlx_whisper`, `whisperx` et `anthropic` ailleurs
dans le toolkit, appliqué un cran plus haut.

**`--summarize` relit le fichier écrit plutôt que le texte en mémoire.** Après
avoir délégué la transcription, `cli.py` relit la sortie et la passe à
`summarize_text()` — exactement le chemin de la sous-commande `summarize`. Le
format `[SPEAKER_XX] texte` garde ainsi une définition unique, dans
`diarize.py`, au lieu d'être reconstruit ici pour l'affichage.

**En lot, le résumé suit la même reprise que la transcription.** `batch
--summarize` résume les fichiers traités **et** ceux sautés parce que leur
transcription existait déjà, mais saute ceux dont le `_summary.txt` est déjà
présent — sauf `--force`. Sans la première règle, reprendre un lot interrompu ne
résumerait que la partie restante ; sans la seconde, chaque relance repaierait
tous les appels à l'API.

**Ce que le CLI unifié n'expose pas.** `--model` (modèle Whisper) et
`--diarization-model` restent accessibles via `python src/transcribe.py` et
`python src/diarize.py`. Ce sont des réglages rares : les exposer sur chaque
sous-commande aurait allongé l'aide sans servir l'usage courant.

**Trois ajustements dans les modules existants**, pour que `cli.py` n'ait rien à
dupliquer : `summarize.summary_path()` (pendant de `transcript_path()`, sans
lequel on ne peut pas savoir qu'un résumé existe déjà), `batch.report_summary()`
(le bilan du lot sort de `main()` pour être appelable des deux côtés), et
`transcribe_youtube()` qui retourne désormais `(texte, chemin de sortie)` — le
nom du fichier produit dépend du titre de la vidéo, connu seulement là.

### `app.py` — interface web, présentation seule

Pendant exact de `cli.py`, dans le navigateur : **aucune** logique de
transcription, de diarisation, de téléchargement ni de résumé n'y est écrite.
Les deux points d'entrée coexistent et appellent les mêmes fonctions, donc une
correction faite dans `src/` vaut pour les deux sans rien recopier.

```
onglet Fichier unique ──> fichier reçu écrit dans un dossier temporaire
                     ──> transcribe_file() | diarize_file()   ──> output/{nom}[_diarized].txt
onglet Dossier        ──> process_folder()                    ──> tableau succès / sautés / échecs
onglet YouTube        ──> transcribe_youtube()                ──> idem
                                     │
                     case « Résumer » ──> summarize_text()    ──> output/{nom}_summary.txt
```

**Le nom du fichier reçu est conservé**, parce que c'est lui qui donne son nom à
la sortie : un `cours.m4a` déposé dans le navigateur produit `output/cours.txt`,
comme en CLI. Il est réduit à son basename avant écriture — il vient du
navigateur, donc de l'extérieur, et un nom comme `../../x.wav` écrirait ailleurs.
L'audio lui-même atterrit dans un dossier temporaire effacé aussitôt : seule la
transcription survit.

**Le champ « dossier » est confiné à une racine autorisée.** C'est le seul
endroit de l'app où l'utilisateur tape un chemin libre. Sans borne, il suffirait
d'exposer l'app sur le réseau — ce que Streamlit fait par défaut, voir
l'avertissement plus haut — pour laisser n'importe qui lister et transcrire
n'importe quel dossier de la machine. La racine est celle du dépôt ;
`WHISPER_TOOLKIT_ROOT` l'élargit en connaissance de cause :

```bash
WHISPER_TOOLKIT_ROOT=~/Documents/cours streamlit run app.py
```

La vérification passe par `os.path.realpath`, qui résout `..` **et** les liens
symboliques : ni `/etc`, ni `../../../../etc`, ni un lien posé dans le dépôt ne
sortent de la racine (vérifié, Test 11). L'usage prévu reste local ; le
garde-fou est posé maintenant plutôt qu'après.

**Les options sont déclarées une fois pour les trois onglets**, comme le parseur
parent `audio` de `cli.py` le fait pour les trois sous-commandes. Les
avertissements que le CLI imprime deviennent ici du grisage : cocher
« Identifier les locuteurs » désactive le champ langue, que whisperx ignorerait.

**Ce que l'app réutilise sans le recopier**, au-delà des fonctions de pipeline :
`cli.summarize_batch()` pour la règle de résumé d'un lot — résumer aussi les
fichiers sautés par la reprise, mais pas ceux dont le `_summary.txt` existe déjà
— et `batch.short_reason()` pour réduire la bannière ffmpeg à une ligne dans le
tableau. Les deux sont **publiques**, et `summarize_batch()` prend des paramètres
explicites plutôt que le `Namespace` d'argparse qu'elle lisait quand elle ne
servait qu'au CLI : c'est le même ajustement que `batch.report_summary()` à
l'étape 8, pour la même raison — une règle qui vaut pour les deux points d'entrée
n'a pas à être écrite deux fois, ni à passer par une ligne de commande fabriquée
pour l'occasion.

**Les imports lourds restent dans les fonctions**, pour la même raison qu'ailleurs
et une de plus : Streamlit ré-exécute le script en entier à chaque interaction,
donc tout ce qui est en tête de fichier est payé à chaque case cochée.

### `batch.py` — orchestration, pas un troisième pipeline

`batch.py` **ne contient aucune logique de traitement audio**. Il liste les
fichiers d'un dossier et délègue, fichier par fichier, à l'un des deux pipelines
ci-dessus :

```
dossier ──> list_audio_files()          (filtre sur SUPPORTED_EXTENSIONS)
        ──> pour chaque fichier :
              sortie déjà présente ? ──> sauté           (sauf --force)
              transcribe_file() + save_transcript()            (défaut)
              diarize_file()    + save_diarized_transcript()   (--diarize)
        ──> {"success": [...], "failed": [(chemin, erreur), ...], "skipped": [...]}
```

Il importe `SUPPORTED_EXTENSIONS` depuis `transcribe.py` au lieu de la
redéfinir : ajouter un format là-bas le rend disponible ici sans rien toucher.

**Robustesse aux échecs partiels.** Chaque fichier est traité dans son propre
`try/except` : un fichier illisible n'interrompt pas le lot. Le résumé final
liste les échecs avec leur raison, et le processus sort en code 1 si au moins un
fichier a échoué — pratique pour enchaîner dans un script.

**Reprise : c'est le comportement par défaut.** Avant de traiter un fichier,
`batch.py` regarde si sa sortie existe déjà dans `output/` ; si oui, il le saute.
Relancer un lot interrompu ne refait donc que ce qui manque. `--force` retraite
tout, sortie existante ou non.

```bash
python src/batch.py mon-dossier/           # reprise : ne refait que ce qui manque
python src/batch.py mon-dossier/ --force   # retraite tout
```

Trois points à connaître :

- **Les fichiers sautés sont comptés à part**, dans `"skipped"`, et listés nommément
  dans le résumé. Ce n'est jamais un skip silencieux : un fichier sauté n'est ni
  un succès ni un échec, et ne change pas le code de sortie.
- **La reprise est par mode.** La sortie attendue est `output/{nom}.txt` en
  transcription et `output/{nom}_diarized.txt` en diarisation : avoir déjà
  transcrit un fichier ne fait pas sauter sa diarisation, et réciproquement.
- **Seule la présence du fichier compte, pas son contenu.** Une sortie tronquée
  par une interruption au milieu d'une écriture sera considérée comme faite ;
  c'est `--force` (ou la suppression du `.txt`) qui la refait. En contrepartie,
  un fichier en échec ne produit aucune sortie, donc il est bien retenté au
  lancement suivant.

Les chemins de sortie viennent de `transcript_path()` et
`diarized_transcript_path()`, exportés par les modules qui les écrivent.
`batch.py` ne réimplémente pas la convention de nommage : changer le suffixe
d'un côté ne peut pas désynchroniser la détection de reprise de l'autre.

**Pas de surveillance continue de dossier.** Un simple traitement de lot couvre
l'usage réel (« transcrire tous les cours de la semaine d'un coup »). Le mode
watchdog ne sera ajouté que si le besoin se confirme.

### `youtube.py` — téléchargement, puis délégation

Comme `batch.py`, ce module ne transcrit rien lui-même : il récupère l'audio
avec yt-dlp et passe la main.

```
URL ──> extract_info()      (titre + identifiant, sans télécharger)
    ──> _safe_stem()        (nom de fichier prévisible)
    ──> download            (test-audio/{nom}.opus, gitignoré)
    ──> transcribe_file()   ou  diarize_file()   (--diarize)
    ──> output/{nom}.txt    ou  output/{nom}_diarized.txt
```

**Format téléchargé : `.opus`, choisi après mesure.** YouTube sert nativement un
flux Opus, que yt-dlp extrait en `-acodec copy` — donc **sans ré-encodage**.
Pour une vidéo d'une minute : **960 Ko en opus contre 11,4 Mo en wav**, où le
wav impose en plus une passe ffmpeg. `.opus` est déjà dans
`SUPPORTED_EXTENSIONS`, donc `transcribe_file()` l'accepte tel quel. La
constante `AUDIO_FORMAT` en tête du module suffit à basculer sur `m4a` ou `wav`.

Le détail qui a tranché : à contenu audio identique, **le conteneur n'a aucun
effet** sur la transcription — un même flux en `.m4a` et en `.wav` donne le même
texte, au mot près, dans le même temps. Ce qui compte est le **flux source
choisi chez YouTube**, pas l'extension. Mesures dans le Test 7 ci-dessous.

**Nommage.** `_safe_stem()` translittère le titre en ASCII et remplace tout le
reste par `_`. Un titre entièrement non latin, vide, ou fait de ponctuation ne
laisse rien d'exploitable : on retombe alors sur l'identifiant YouTube. Effet de
bord utile : un titre comme `../../etc/passwd` devient `etc_passwd`, donc aucune
écriture hors de `test-audio/`. En contrepartie, **deux vidéos de même titre
écrivent le même fichier** — c'est le prix d'un nom prévisible.

**Langue : détection automatique**, comme partout ailleurs depuis que le défaut
`fr` a été retiré de `transcribe_file()` — voir « Langue » ci-dessous.

### `summarize.py` — la seule étape qui sort de la machine

Tout le reste du toolkit tourne en local. `summarize.py` envoie du texte à
l'API Claude : c'est le seul module qui expose du contenu à un service externe,
et la seule fonctionnalité qui coûte de l'argent.

```
transcription (.txt) ──> summarize_text()   (API Claude)
                     ──> output/{nom}_summary.txt
```

**Il prend un fichier texte, jamais de l'audio.** Le résumé est une étape
séparée qui s'enchaîne après la transcription, pas un mode de plus dans
`transcribe.py` : on résume un texte déjà produit, éventuellement corrigé à la
main, sans repayer une transcription.

```bash
python src/transcribe.py cours.m4a          # produit output/cours.txt
python src/summarize.py output/cours.txt    # produit output/cours_summary.txt
```

**Clé API.** Elle est lue dans `.env` sous `ANTHROPIC_API_KEY`, même mécanisme
que `HF_TOKEN` — voir « Clé API Anthropic » plus bas. `load_dotenv()` cherche
le `.env` à partir du fichier appelant, donc le CLI marche depuis n'importe
quel répertoire.

**Le prompt système décrit la matière, pas seulement la tâche.** Il dit au
modèle que le texte sort d'une reconnaissance vocale — mots mal reconnus,
ponctuation approximative, hésitations — et qu'il doit lire à travers ces
défauts sans les commenter. Il lui dit aussi que les étiquettes `[SPEAKER_00]`
d'une sortie diarisée sont des identifiants arbitraires et non des noms. Sans
ça, le modèle a tendance soit à commenter la qualité de la transcription, soit
à inventer des noms de locuteurs.

**Le paramètre `style` est du texte libre**, injecté tel quel dans le prompt
(`concis` par défaut, mais `en trois puces` ou `pour quelqu'un qui n'était pas
là` marchent aussi). Pas d'énumération fermée : le modèle comprend la consigne
en toutes lettres, une table de correspondance n'apporterait rien.

**Modèle par défaut : `claude-sonnet-5`.** `--model` permet d'en changer au cas
par cas, `claude-opus-5` étant le plus capable si le besoin s'en fait sentir.

**Garde-fou d'entrée : 150 000 caractères.** Très en dessous de la fenêtre de
contexte du modèle — il ne protège pas l'API, il transforme un refus distant
obscur en erreur locale lisible, **avant** de payer l'appel. Au-delà, le module
refuse et invite à découper : il n'y a pas de découpage automatique, et ce n'est
pas prévu tant que l'usage reste des réunions et des cours.

Les imports entre modules de `src/` sont **plats** (`from transcribe import …`),
parce que ces fichiers s'exécutent comme des scripts : `python src/batch.py`
place `src/` en tête de `sys.path`. Un `python -m src.batch` ne fonctionnerait
pas sans imports relatifs.

### Pipeline de `diarize.py`

```
audio ──> whisperx.load_model + transcribe   (faster-whisper, CPU)
      ──> whisperx.load_align_model + align  (wav2vec2, timings au mot)
      ──> DiarizationPipeline                (pyannote, modèle sous conditions)
      ──> whisperx.assign_word_speakers      (segments étiquetés)
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

`ffmpeg` doit être disponible dans le `PATH` (requis par `yt-dlp` et par les
backends Whisper).

### Token Hugging Face (diarisation uniquement)

`diarize.py` s'appuie sur `pyannote/speaker-diarization-community-1`, un modèle
**sous conditions d'accès**. Il faut donc :

1. créer un token sur [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) ;
2. accepter les conditions du modèle sur sa page Hugging Face ;
3. le placer dans un fichier `.env` à la racine (déjà ignoré par git) :

```
HF_TOKEN=hf_xxxxxxxxxxxxxxxx
```

Le token peut aussi être passé directement en argument à `diarize_file()`.
`transcribe.py` n'en a pas besoin.

### Clé API Anthropic (résumé uniquement)

`summarize.py` appelle l'API Claude, qui est **payante** — c'est la seule
fonctionnalité du toolkit qui consomme un budget. Crée une clé sur
[console.anthropic.com](https://console.anthropic.com/settings/keys) et
place-la dans le même `.env` :

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` est ignoré par git (`.gitignore:24`, vérifié avec `git check-ignore`) et
n'a jamais été suivi. Aucune clé n'apparaît dans les messages d'erreur du
module : ils citent le nom de la variable et l'URL de la console, jamais la
valeur.

Les autres modules n'en ont pas besoin — l'import d'`anthropic` est paresseux,
donc le reste du toolkit fonctionne même sans le paquet installé.

### Cache NLTK — `.nltk_data/`

Pendant l'alignement, whisperx télécharge le tokenizer de phrases `punkt_tab`
(~4 Mo) via NLTK. Par défaut NLTK l'écrit dans `~/nltk_data`, à la racine du
compte utilisateur. `diarize.py` redirige ce cache vers `.nltk_data/` à la
racine du repo, pour que tout ce qui concerne le projet reste dans le projet.

`.nltk_data/` est un **cache local, régénérable, jamais committé** : il est
dans `.gitignore`, ne contient que des données tierces téléchargées, et se
reconstruit tout seul au prochain lancement. Il peut être supprimé à tout
moment — le seul coût est un re-téléchargement.

La redirection se fait en tête de `diarize.py`, et repose sur deux détails de
NLTK qu'il ne faut pas « simplifier » :

- **`os.environ["NLTK_DATA"]` doit être posé avant `import nltk`.** À l'import,
  `nltk.downloader` instancie un singleton dont le dossier de destination est
  figé une fois pour toutes. Un `nltk.data.path.insert()` après coup corrige
  la *lecture* du cache, mais plus son *écriture* : le téléchargement repart
  dans `~/nltk_data`.
- **Le dossier doit exister avant l'import.** NLTK ne retient un chemin que
  s'il existe et est writable. Comme `.nltk_data/` est gitignoré, il est absent
  d'un clone frais : d'où le `os.makedirs(..., exist_ok=True)`.

`batch.py` hérite de la configuration en important `diarize` ;
`transcribe.py` (mlx-whisper) ne touche ni à whisperx ni à NLTK.

## État d'installation par machine

### ⚠️ Mac M5 (Apple Silicon) — machine cible, pas encore configurée

**`mlx-whisper` doit être installé sur le Mac M5.** Le paquet repose sur le
framework MLX d'Apple et ne s'installe que sur macOS Apple Silicon. Il est
présent dans `requirements.txt` avec un marqueur d'environnement
(`sys_platform == "darwin" and platform_machine == "arm64"`) : il est donc
installé automatiquement sur le Mac, et ignoré silencieusement ailleurs.

Sur le Mac, un simple `pip install -r requirements.txt` suffit.

### Machine de dev actuelle — Windows 11, x86_64 (AMD64), Python 3.14.6

Ce n'est pas un Mac Apple Silicon, donc `mlx-whisper` n'y est **pas** installé.

| Paquet | Statut |
|---|---|
| `yt-dlp` | ✅ installé (2026.7.4) |
| `whisperx` | ❌ **non installé** — incompatible avec Python 3.14 |
| `mlx-whisper` | ⏭️ ignoré (Apple Silicon uniquement) |

**Pourquoi whisperx échoue ici :** toutes les versions récentes de `whisperx`
déclarent `Requires-Python >=3.10,<3.14`. pip retombe alors sur la vieille
version 3.2.0, qui épingle `ctranslate2==4.4.0` — un paquet qui n'a aucune roue
pour Python 3.14. L'installation s'arrête sur :

```
ERROR: No matching distribution found for ctranslate2==4.4.0
```

**Correctif :** recréer le venv avec Python 3.12 (ou 3.13), puis réinstaller :

```powershell
py -3.12 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 3.12 n'est pas encore installé sur cette machine (seul 3.14 l'est).
Ce point est sans impact sur la machine cible : sur le Mac M5, il suffit
d'utiliser un Python 3.12/3.13 pour le venv.

## Testing Status

Suivi de ce qui est **écrit** vs ce qui est **réellement exécuté**. « Testé »
signifie ici : lancé pour de vrai et sortie vérifiée — pas seulement compilé.
À mettre à jour à chaque étape.

| Module / fonction | Écrit | Compile | Exécuté pour de vrai | Notes |
|---|---|---|---|---|
| `src/transcribe.py` | ✅ | ✅ | ✅ | validé de bout en bout le 2026-08-06 |
| └ `transcribe_file()` | ✅ | ✅ | ✅ | `whisper-large-v3-mlx`, langue détectée, `.m4a` `.wav` `.opus` `.ogg` |
| └ `save_transcript()` | ✅ | ✅ | ✅ | fichiers `output/*.txt` créés et relus |
| └ CLI `argparse` | ✅ | ✅ | ✅ | `--help`, run nominal, codes de sortie |
| └ erreur fichier absent | ✅ | ✅ | ✅ | message clair + `exit 1` |
| └ erreur extension | ✅ | ✅ | ✅ | message clair + `exit 1` |
| `src/diarize.py` | ✅ | ✅ | ✅ | pipeline complet validé le 2026-08-06 |
| └ ASR faster-whisper | ✅ | ✅ | ✅ | `large-v3` int8 CPU, langue `fr` détectée seule |
| └ alignement wav2vec2 | ✅ | ✅ | ✅ | 9 mots alignés, timings au mot |
| └ `DiarizationPipeline` | ✅ | ✅ | ✅ | **2 locuteurs sur 2 séparés correctement** |
| └ `assign_word_speakers()` | ✅ | ✅ | ✅ | labels distincts sur les deux segments |
| └ `save_diarized_transcript()` | ✅ | ✅ | ✅ | format `[SPEAKER_XX] texte` vérifié |
| └ `diarization_model` | ✅ | ✅ | ✅ | testé via `--diarization-model` sur un autre dépôt |
| └ `_resolve_token()` | ✅ | ✅ | ✅ | absence de token détectée, message clair |
| └ erreur 401 vs 403 | ✅ | ✅ | ✅ | messages distincts, vérifiés en vrai HTTP |
| └ erreur fichier absent | ✅ | ✅ | ✅ | message clair + `exit 1` |
| └ `--num-speakers` | ✅ | ✅ | ✅ | `2` respecté sur la fixture 2 voix |
| `src/batch.py` | ✅ | ✅ | ✅ | validé le 2026-08-07 |
| └ `list_audio_files()` | ✅ | ✅ | ✅ | filtre extensions, ignore `.txt` et sous-dossiers |
| └ `process_folder()` | ✅ | ✅ | ✅ | mode transcription et mode `--diarize` |
| └ échec partiel | ✅ | ✅ | ✅ | **le lot continue**, 2/3 traités sur fichier corrompu |
| └ `--num-speakers` propagé | ✅ | ✅ | ✅ | borne `[2, 2]` bien reçue par pyannote |
| └ `short_reason()` | ✅ | ✅ | ✅ | bannière ffmpeg de 13 lignes réduite à 1 |
| └ dossier introuvable / vide | ✅ | ✅ | ✅ | `exit 1` / `exit 0` avec message |
| `src/youtube.py` | ✅ | ✅ | ✅ | validé le 2026-08-07 (Test 7) |
| └ `transcribe_youtube()` | ✅ | ✅ | ✅ | retourne `(texte, chemin)` depuis l'étape 8 |
| `src/summarize.py` | ✅ | ✅ | ✅ | `claude-sonnet-5`, 26/26 faits capturés sur 2 411 mots, ≈ 0,039 $ (Test 9) |
| └ `summary_path()` | ✅ | ✅ | ✅ | ajouté à l'étape 8, exercé par la reprise de `batch --summarize` |
| `src/cli.py` | ✅ | ✅ | ✅ | validé le 2026-08-07 (Test 10) |
| └ `transcribe` | ✅ | ✅ | ✅ | seul, et avec `--diarize --num-speakers 2 --summarize` |
| └ `batch` | ✅ | ✅ | ✅ | 2 succès / 1 échec isolé, reprise à deux niveaux |
| └ `youtube` | ✅ | ✅ | ✅ | vidéo NASA, avec `--summarize` |
| └ `summarize` | ✅ | ✅ | ✅ | `--model claude-haiku-4-5` et `--style` vérifiés |
| └ `--summarize` enchaîné | ✅ | ✅ | ✅ | sur les trois entrées audio |
| └ avertissements d'options | ✅ | ✅ | ✅ | `--num-speakers` sans `--diarize`, `--language` avec |
| └ codes de sortie | ✅ | ✅ | ✅ | `0` / `1`, échec partiel de lot compris |
| └ imports paresseux | ✅ | ✅ | ✅ | `--help` en 0,03 s contre 0,72 s en imports directs |
| `app.py` | ✅ | ✅ | ✅ | validé le 2026-08-07 dans un vrai navigateur (Test 11) |
| └ onglet *Fichier unique* | ✅ | ✅ | ✅ | upload → `output/two_voices_generated.txt` |
| └ onglet *Dossier (batch)* | ✅ | ✅ | ✅ | 2 succès / 1 échec isolé, puis reprise 2 sautés |
| └ onglet *YouTube* | ✅ | ✅ | ✅ | vidéo NASA, seule ou avec résumé enchaîné |
| └ case « Résumer » | ✅ | ✅ | ✅ | appel réel, résumé affiché et écrit dans `output/` |
| └ racine autorisée | ✅ | ✅ | ✅ | `/etc` et `../../../../etc` refusés |
| └ grisage langue / locuteurs | ✅ | ✅ | ✅ | équivalent des avertissements du CLI |
| `src/__init__.py` | ✅ (vide) | ✅ | n/a | simple marqueur de package |
| Surveillance de dossier | ❌ | — | — | volontairement non implémentée |
| `tests/` | ❌ vide | — | — | aucun test automatisé |

### Transcriptions réelles exécutées (2026-08-06)

Les fichiers audio de test vivent dans `test-audio/`, **ignoré par git** — ce
dépôt est public, aucun enregistrement réel ne doit y être versionné. Seule
exception : la fixture entièrement synthétique du test 4. Le contenu des
transcriptions d'enregistrements réels n'est pas reproduit ici, même raison.

**Test 1 — échantillon synthétique (voix macOS `Thomas`, fr_FR, 6,3 s, `.m4a`)**

| | |
|---|---|
| **Texte attendu** | « Bonjour, ceci est un test de transcription pour le projet whisper toolkit. Il fait beau aujourd'hui à Paris. » |
| **Texte obtenu** | « Bonjour, ceci est un test de transcription pour le projet Wisp et Tolkien. Il fait beau aujourd'hui à Paris. » |

Seul écart : « whisper toolkit » → « Wisp et Tolkien ». C'est un artefact de
l'échantillon, pas du modèle — la voix française prononce ces deux mots anglais
à la française, et Whisper transcrit fidèlement ce qu'il entend. Ponctuation,
accents et apostrophes sont corrects.

**Test 2 — vocal WhatsApp réel (voix humaine, fr, 2,47 s)**

Source : `.opus` mono 48 kHz (conteneur ogg, 18,6 kbit/s). Transcription
**correcte** : phrase cohérente, ponctuation et accents corrects, malgré la
forte compression WhatsApp et une durée très courte. Contenu non reproduit
(dépôt public).

Le même extrait a été passé sous quatre formes — `.opus`, `.ogg` (opus remuxé),
`.ogg` (vorbis stéréo) et `.wav` 16 kHz mono — avec une sortie **identique au
caractère près** dans les quatre cas.

> **Pourquoi aucune conversion n'est faite dans le code.** `mlx_whisper`
> décode déjà tout via ffmpeg, en imposant lui-même 16 kHz mono
> (`ffmpeg -i <fichier> -f s16le -ac 1 -ar 16000 -`, cf. `mlx_whisper/audio.py`).
> Convertir en amont referait donc exactement le même travail, en double et avec
> un fichier temporaire à gérer. `SUPPORTED_EXTENSIONS` sert uniquement de
> garde-fou pour rejeter tôt un fichier manifestement non audio ; tout format lu
> par ffmpeg fonctionne dès qu'il y figure.

**Performance** (Mac M5, `whisper-large-v3-mlx`) :

| Run | Durée | Détail |
|---|---|---|
| 1er | 4 min 16 s | dont 3 min 49 s de téléchargement du modèle (~3 Go) |
| Suivants | 3,1 – 3,6 s | modèle en cache, pour 2,5 – 6,3 s d'audio |

Le temps est dominé par le chargement du modèle, pas par la durée de l'audio :
ces mesures ne disent rien du débit sur un fichier long.

### Test 3 — `diarize.py`, pipeline complet validé (2026-08-06)

**La diarisation tourne de bout en bout.** Après acceptation des conditions de
`pyannote/speaker-diarization-community-1`, le pipeline entier s'exécute sans
erreur sur le vocal WhatsApp (2,47 s, `.opus`) :

| Étape du pipeline | Statut | Détail mesuré |
|---|---|---|
| `whisperx.load_audio` | ✅ | 39 256 échantillons à 16 kHz |
| `whisperx.load_model` | ✅ | `large-v3` int8 CPU |
| VAD pyannote | ✅ | exécutée sans erreur |
| `.transcribe()` | ✅ | langue `fr` détectée seule (confiance 1.00), 1 segment |
| `load_align_model` + `align` | ✅ | 9 mots alignés, segment 0,28 s → 2,40 s |
| `DiarizationPipeline` | ✅ | `community-1` chargée sur CPU |
| `assign_word_speakers` | ✅ | clé `speaker` présente sur le segment |
| `save_diarized_transcript()` | ✅ | fichier `output/..._diarized.txt` écrit et relu |

Sortie : une ligne au format `[SPEAKER_00] <texte>`, soit exactement le format
attendu (contenu non reproduit, dépôt public). **Run complet : 18,1 s**, modèles
en cache.

Un seul locuteur ici, l'échantillon étant mono-locuteur : ce test valide
l'exécution du pipeline, pas la séparation des voix. Celle-ci fait l'objet du
test 4.

**Historique du blocage** (résolu). Le premier run avec token valide échouait
en **403** : les conditions de `community-1` n'avaient pas été acceptées sur le
compte, alors que celles de la famille 3.1 l'étaient. Aucun contournement par
paramètre n'existait — avec `pyannote.audio` 4.0.7, pointer explicitement
`speaker-diarization-3.1` réclame quand même `plda/xvec_transform.npz`, hébergé
dans `community-1`, et retombe sur un 401.

> ℹ️ **Le token n'est requis qu'au premier téléchargement.** Une fois les poids
> pyannote en cache local, `Pipeline.from_pretrained` ne le consulte plus : un
> token invalide, ou absent, passe alors sans erreur. Constaté en tentant de
> rejouer les cas d'erreur après un run réussi.

**Écart entre les deux backends.** Sur le même extrait, faster-whisper et
mlx-whisper produisent des transcriptions qui diffèrent d'un mot (58 vs
57 caractères). Rien d'anormal — deux implémentations, deux quantifications —
mais à garder en tête : les deux pipelines ne sont pas interchangeables au
caractère près.

**Le coût du CPU est mesuré, pas supposé** (modèles en cache) :

| Étape | Durée |
|---|---|
| `load_model` | 5,6 s |
| `.transcribe()` | **10,4 s** pour 2,47 s d'audio |
| `load_align_model` | 0,3 s |
| `align` | 0,1 s |
| **Total** | **17,6 s** |

Soit **~4× plus lent que le temps réel** sur la seule transcription, là où
`transcribe.py` traite le même fichier en 3,1 s de bout en bout — l'écart
attendu entre MLX/Metal et CTranslate2/CPU. Premier run : 15 min 42, dominé par
le téléchargement des modèles (`large-v3` CTranslate2 + wav2vec2 français).

**Erreurs vérifiées en conditions réelles :**

Les trois cas de token sont désormais **distingués**, chacun vérifié contre une
vraie réponse HTTP :

| Cas | Message produit | Vérifié avec |
|---|---|---|
| Token absent | « Token Hugging Face introuvable » + lien vers les réglages de token | `load_dotenv` neutralisé, `HF_TOKEN` retiré |
| Token invalide (**401**) | « Token refusé » → régénérer le token | token bidon sur un dépôt gated non caché |
| Conditions non acceptées (**403**) | « Accès refusé au modèle *X* » → lien direct vers la page HF **du modèle demandé** | token valide sur `pyannote/speaker-diarization` |
| Fichier introuvable | `Fichier introuvable : ...` | chemin inexistant |

Les quatre sortent en `exit 1`. Le cas 403 nomme le modèle réellement demandé,
donc le lien reste correct même avec `--diarization-model`.

### Test 4 — séparation de deux locuteurs (2026-08-07)

Premier test qui valide la **raison d'être** de la diarisation, et non seulement
son exécution. Fixture : `test-audio/two_voices_generated.wav`, 9,5 s.

**Vérité terrain**, établie par mesure et non par confiance :

| | |
|---|---|
| Voix 1 | `Amélie` (fr_CA), F0 médiane **225 Hz**, 0 → 4,06 s |
| Voix 2 | `Thomas` (fr_FR), F0 médiane **128 Hz**, 4,06 → 9,48 s |
| Bascule | **4,06 s** (fin de la première réplique) |

**Résultat**, avec `--num-speakers 2` :

| start | end | speaker | voix réelle |
|---|---|---|---|
| 0,23 s | 4,08 s | `SPEAKER_01` | Amélie |
| 4,13 s | 9,36 s | `SPEAKER_00` | Thomas |

| Critère | Attendu | Obtenu | |
|---|---|---|---|
| Nombre de locuteurs | 2 | 2 | ✅ |
| Nombre de segments | 2 | 2 | ✅ |
| Point de bascule | 4,06 s | 4,08 – 4,13 s | ✅ à **±70 ms** |
| Mélange de voix | aucun | aucun | ✅ |

L'écart de 20 à 70 ms correspond au silence entre les deux répliques : les
bornes tombent de part et d'autre de la jonction réelle. Run complet : 17,5 s.

> ⚠️ **Les labels `SPEAKER_XX` ne suivent pas l'ordre d'apparition.** Ici Amélie
> parle en premier et reçoit `SPEAKER_01`, tandis que Thomas reçoit
> `SPEAKER_00`. Ne jamais supposer que `SPEAKER_00` est le premier à parler :
> les identifiants sont arbitraires et stables seulement à l'intérieur d'un run.

**À propos de la fixture.** `test-audio/two_voices_generated.wav` est le seul
fichier audio versionné du dépôt (exception explicite dans `.gitignore`). Il est
**intégralement synthétique**, généré avec la commande macOS `say` à partir de
deux voix système, puis concaténé avec ffmpeg :

```bash
say -v "Amélie" -o a.aiff "…"      # attention à l'accent, voir ci-dessous
say -v Thomas   -o b.aiff "…"
# conversion en wav 16 kHz mono, puis concat ffmpeg
```

Aucune voix réelle, aucune donnée personnelle. Il sert de fixture de
non-régression pour `diarize.py`.

> ⚠️ **Piège `say` : le nom de voix doit être exact, accents compris.**
> `say -v Amelie` (sans accent) ne lève **aucune erreur** — la commande retombe
> silencieusement sur la voix par défaut. On obtient alors deux extraits de la
> *même* voix, et une fixture qui ne teste rien. Le contrôle qui l'a révélé :
> mesurer la F0 des deux extraits avant de s'en servir. 225 Hz contre 128 Hz
> valide la fixture ; deux valeurs voisines la disqualifient.

### Test 5 — `batch.py`, robustesse aux échecs partiels (2026-08-07)

Dossier de test monté hors dépôt, contenant volontairement de quoi faire échouer
le lot :

| Fichier | Nature | Attendu |
|---|---|---|
| `01_deux_voix.wav` | fixture synthétique 2 voix, 9,5 s | traité |
| `02_vocal.wav` | enregistrement réel, mono-locuteur | traité |
| `03_corrompu.wav` | fichier texte renommé en `.wav` | **échec isolé** |
| `04_ignore.txt` | extension non audio | ignoré au listage |
| `sous_dossier/` | répertoire | ignoré au listage |

**Résultat, mode transcription** (`python src/batch.py <dossier>`) :

| Critère | Obtenu | |
|---|---|---|
| Fichiers listés | 3 sur 5 entrées | ✅ `.txt` et dossier écartés |
| Traités avec succès | 2 | ✅ |
| Échecs | 1 (`03_corrompu.wav`) | ✅ isolé |
| Le lot s'est poursuivi après l'échec | oui | ✅ |
| Sortie produite pour le fichier en échec | aucune | ✅ |
| Code de sortie | 1 | ✅ échec partiel signalé |
| Durée | 6,9 s | |

**Résultat, mode diarisation** (`--diarize --num-speakers 2`) : même comptage,
2 succès et 1 échec isolé, sorties `*_diarized.txt` produites, 39,5 s. La borne
`--num-speakers 2` est bien parvenue à pyannote — il l'a signalée comme
inatteignable sur le fichier mono-locuteur, ce qui confirme la propagation du
paramètre à travers `batch.py`.

Cas limites vérifiés séparément : dossier inexistant → message clair et `exit 1` ;
dossier sans aucun fichier audio → message et `exit 0`, sans erreur.

> **Lisibilité du résumé.** Quand ffmpeg échoue, il recrache sa bannière de
> compilation : l'erreur brute du fichier corrompu fait **13 lignes et
> 1173 caractères**, ce qui noyait tout le résumé du lot. `short_reason()` la
> réduit à sa première ligne pour l'affichage. L'erreur complète reste
> accessible dans le dict retourné par `process_folder()`.

### Test 6 — reprise de `batch.py` (2026-08-07)

Exécuté sur `test-audio/`, qui contient **6 fichiers tous traitables**
(`.opus`, `.ogg` ×2, `.wav` ×3), après avoir mis `output/` de côté pour partir
d'un état vierge. Trois lancements successifs, en mode transcription :

| # | Commande | Traités | Sautés | Sortie |
|---|---|---|---|---|
| 1 | `batch.py test-audio/` | 6 | 0 | 6 `.txt` créés, 8,7 s |
| 2 | `batch.py test-audio/` | 0 | **6** | aucune réécriture, `exit 0` |
| 3 | `batch.py test-audio/ --force` | 6 | 0 | 6 `.txt` réécrits |

Le run 3 a été validé sur les **mtimes** et non sur le seul affichage : les six
horodatages passent de `12:03:4x` à `12:04:0x`, donc les fichiers ont réellement
été réécrits, pas simplement re-annoncés.

Cas complémentaires vérifiés :

| Scénario | Attendu | Obtenu |
|---|---|---|
| Suppression d'**une** sortie sur 6, relance | 1 traité, 5 sautés | ✅ |
| `--diarize` alors que les 6 `.txt` existent | rien de sauté | ✅ 2/2 diarisés |
| `--diarize` relancé après coup | 2 sautés | ✅ |
| Transcription relancée après diarisation | 2 sautés | ✅ |

> **Le test qui compte vraiment est celui du croisement des modes.** Une
> implémentation naïve qui chercherait « une sortie quelconque pour ce fichier »
> aurait sauté la diarisation de fichiers déjà transcrits — et le lot aurait
> paru réussir en ne produisant rien. C'est pourquoi la sortie attendue est
> demandée à `transcript_path()` / `diarized_transcript_path()` selon le mode,
> plutôt que reconstruite dans `batch.py`.

### Test 7 — `youtube.py` (2026-08-07)

Vidéo de test : `V0oo_Nybo6w`, « NASA Artemis II: Counting Down to Our Next Moon
Mission », 60 s, chaîne officielle NASA. Choisie parce qu'une production de la
NASA est dans le domaine public (œuvre du gouvernement américain) et que sa
durée garde le test rapide. **Ni l'audio ni la transcription ne sont versionnés**
— `test-audio/*` et `output/` sont ignorés, vérifié avec `git check-ignore`.

**Choix du format : mesuré, pas supposé.** Le point de départ était « `.wav` ou
`.m4a` ». La mesure a montré que la question était mal posée.

| Source | Conteneur | Temps | Mots | Réf. sous-titres |
|---|---|---|---|---|
| flux AAC | `.m4a` | 20,1 s | 338 | 121 |
| flux AAC | `.wav` | 20,3 s | 338 | 121 |
| flux Opus | `.m4a` | 5,0 s | 124 | 121 |
| flux Opus | `.wav` | 5,0 s | 123 | 121 |

À contenu identique, les deux conteneurs donnent **exactement** le même résultat
(3 exécutions chacun, chiffres stables au dixième). Le conteneur n'entre donc pas
en compte ; seul le **flux source** compte. Sur cette vidéo, le flux AAC part en
boucle d'hallucination : 338 mots au lieu de 121, dont `the` **77 fois**, soit
23 % du texte.

Vérifié sur 3 autres vidéos NASA courtes, transcription comparée aux sous-titres
automatiques YouTube pris comme référence :

| Vidéo | AAC | Opus | Réf. |
|---|---|---|---|
| `XYMuC2MDbwo` | 7,8 s / 176 mots | 6,1 s / 179 mots | 168 |
| `MLgYJh6OFbY` | 36,5 s / 143 mots | 15,1 s / 130 mots | 130 |
| `oqRwrlJbjOg` | 33,3 s / 141 mots | 5,6 s / 132 mots | 131 |

Le flux Opus est plus rapide dans les 4 cas (jusqu'à 6×) et plus proche de la
référence. D'où le choix de `.opus` : meilleure entrée pour Whisper, aucun
ré-encodage (`-acodec copy`, vérifié dans la ligne de commande ffmpeg émise par
yt-dlp), et 12× plus léger que le wav.

> ⚠️ **Le premier run réel a produit une transcription entièrement fausse.**
> L'audio est anglais, mais `transcribe.py` forçait alors `language="fr"` :
> Whisper a rendu un texte français inventé, fluide et plausible, qui n'avait
> qu'un rapport lointain avec l'original. Rien dans la sortie ne signalait le
> problème. Après correction, la transcription correspond aux sous-titres
> YouTube (123 mots contre 121 de référence).
>
> Le correctif appliqué ici était local à `youtube.py`. Le défaut valait aussi
> pour `transcribe.py` et `batch.py` : il a été retiré à la racine au Test 8.

**Résultats fonctionnels :**

| Scénario | Attendu | Obtenu |
|---|---|---|
| CLI, détection auto | transcription anglaise correcte | ✅ 8,6 s bout en bout |
| CLI, `--language en` | identique | ✅ |
| CLI, `--diarize` | segments étiquetés | ✅ 13 segments, 2 locuteurs, 73,5 s |
| Audio téléchargé | dans `test-audio/`, ignoré | ✅ `.gitignore:44` |
| Transcription | dans `output/`, ignorée | ✅ `.gitignore:54` |

**Gestion d'erreurs**, messages vérifiés sur de vraies URL :

| Cas | Obtenu |
|---|---|
| Identifiant inexistant | « Vidéo indisponible … supprimée, privée, ou identifiant erroné » |
| Chaîne qui n'est pas une URL | idem (yt-dlp la traite comme un identifiant) |
| URL non-YouTube en 404 | « Échec du téléchargement » + détail yt-dlp |
| URL de playlist pure | refus explicite, « 8 vidéos … passe l'URL d'une vidéo » |
| URL `watch?v=…&list=…` | la seule vidéo est traitée, titre conservé |

> ⚠️ **Une URL de playlist aurait téléchargé 8 vidéos sous un seul nom.**
> `noplaylist` ne règle que les URL `watch?v=…&list=…` ; sur une URL de
> playlist pure, yt-dlp renvoie les 8 entrées. Comme le modèle de nom est fixé
> avant le téléchargement, les 8 fichiers se seraient écrasés l'un l'autre et
> seule la dernière vidéo aurait été transcrite — sous le titre de la playlist,
> sans le moindre avertissement. D'où le refus explicite dans `download_audio()`.
>
> Le garde-fou a lui-même coûté une correction : `extract_flat=True`, ajouté
> pour ne pas résoudre les 8 entrées, aplatissait *aussi* la vidéo seule, qui
> perdait son titre et retombait sur l'identifiant. C'est `in_playlist` qu'il
> faut, pas `True`.

Le message brut de yt-dlp était affiché **en plus** du message traduit :
`quiet=True` ne couvre pas les erreurs, qui partent sur stderr quoi qu'il
arrive. Un `logger` muet passé à `YoutubeDL` règle le problème.

Cas **non testés** faute de pouvoir les provoquer : vidéo réellement privée,
vidéo bloquée par région. Leur détection repose sur des motifs de message
(`private video`, `not available in your country`) repris de la documentation
yt-dlp, jamais déclenchés en conditions réelles.

Nommage vérifié unitairement — accents translittérés (`Café à la crème` →
`Cafe_a_la_creme`), titre japonais et titre de ponctuation pure repliés sur
l'identifiant, troncature à 80 caractères, et `../../etc/passwd` neutralisé en
`etc_passwd`.

### Test 8 — détection de langue généralisée (2026-08-07)

Le défaut `language="fr"` de `transcribe_file()` est retiré. Le défaut touchait
aussi `batch.py`, qui appelait `transcribe_file()` sans argument : le Test 7
n'avait mis en évidence qu'un symptôme sur trois.

**Aucune dégradation** sur du contenu français, mesurée avant de changer le
défaut. Pour chaque fixture, `language="fr"` puis `language=None` :

| Fixture | forcé `fr` | auto | détecté | texte |
|---|---|---|---|---|
| `conversation_test.wav` | 0,85 s | 1,21 s | `fr` | identique |
| `two_voices_generated.wav` | 1,40 s | 1,78 s | `fr` | identique |
| `whatsapp_test.wav` | 0,79 s | 1,17 s | `fr` | identique |
| `WhatsApp Audio ….opus` | 0,79 s | 1,17 s | `fr` | identique |
| `test_vorbis.ogg` | 0,79 s | 1,14 s | `fr` | identique |

Le texte est **strictement identique** dans les cinq cas — la détection ne change
pas le résultat, elle évite seulement de le corrompre quand la langue diffère.

Le surcoût est **fixe, pas proportionnel** : constant autour de 0,35 s sur ces
fixtures courtes, et 0,32 s sur un fichier français de 76 s (61,39 s → 61,71 s,
soit 0,5 %). La détection ne tourne qu'une fois, sur la première fenêtre.

> ⚠️ **Forcer la langue produit une traduction, pas une erreur.** La fixture
> française passée en `--language en` ressort en anglais parfaitement fluide :
> « Hello, did you have time to look at the supplier's file this morning? » là
> où l'audio dit « Bonjour, est-ce que tu as eu le temps de regarder le dossier
> fournisseur ce matin ? ». Aucun avertissement, aucun code d'erreur, une sortie
> plausible. C'est le même défaut qu'au Test 7, reproduit en sens inverse — et
> la raison pour laquelle un défaut de langue codé en dur n'a pas sa place ici.

**Vérifications fonctionnelles :**

| Scénario | Obtenu |
|---|---|
| `transcribe.py` sans `--language` sur fixture fr | ✅ français correct |
| `transcribe.py --language en` sur la même | ✅ traduit — défaut reproduit |
| `batch.py --force` sur `test-audio/` **mixte** | ✅ 7/7, chacun dans sa langue |
| `batch.py --language en` | ✅ forçage propagé jusqu'à `transcribe_file()` |
| `batch.py --force` ensuite | ✅ retour au français |

Le lot mixte est le test qui compte : `test-audio/` contient 6 fichiers français
et la vidéo NASA anglaise du Test 7. Un seul passage les transcrit chacun dans
sa langue. Avec l'ancien défaut, la vidéo anglaise serait ressortie en français
inventé, sans que le résumé du lot signale quoi que ce soit.

`youtube.py` perd du même coup son `kwargs.setdefault("language", None)`, qui
n'était qu'un contournement local du défaut désormais supprimé.

### Test 9 — `summarize.py`, appel réel sur transcription longue (2026-08-07)

Premier test avec des crédits sur le compte : l'appel à l'API a bien eu lieu et
un résumé a été produit. Le blocage du premier essai (`HTTP 400`, solde
insuffisant) est levé — la branche d'erreur correspondante reste en place et
avait été validée à ce moment-là.

**Sur le texte de test.** Les transcriptions de `output/` totalisent moins de
400 mots à elles toutes : les concaténer ne donnait pas un cas représentatif.
La transcription de test est donc **rédigée à la main** — une réunion de suivi
de projet en français, **2 411 mots / 14 495 caractères**, avec étiquettes
`[SPEAKER_XX]`, hésitations, répétitions et phrases interrompues.

> ⚠️ Elle **simule** une sortie de reconnaissance vocale, elle n'en est pas une.
> Les défauts sont plausibles mais choisis ; un vrai ASR se trompe autrement, en
> particulier sur les noms propres et les chiffres. Ce test valide le
> comportement du résumé sur un texte long et bruité, pas sa robustesse aux
> erreurs réelles de Whisper.

En contrepartie, comme le texte est écrit, **on connaît la vérité terrain** :
26 faits vérifiables y ont été placés délibérément — décisions, actions,
montants, dates, un désaccord tranché et un sujet volontairement non tranché.

**Mesures du run :**

| | |
|---|---|
| Modèle | `claude-sonnet-5` |
| Durée | 15,1 s |
| Tokens | 6 935 en entrée, 1 237 en sortie |
| Coût | ≈ **0,039 $** par résumé (tarif Sonnet 3 $/15 $ par MTok) |
| Compression | 470 mots pour 2 400, soit 20 % |
| `stop_reason` | `end_turn` — pas de troncature |

**Couverture : 26 / 26 faits plantés retrouvés**, vérifiés par script et non à
l'œil. Y compris les détails secondaires (12 000 utilisateurs de l'ancien
portail, pénalités contractuelles plafonnées à ~3 000 €) qu'un premier run avait
laissés de côté — la couverture varie donc d'un appel à l'autre.

**Aucune invention.** Contrôle systématique de la sortie : les seize valeurs
numériques du résumé (240 000 €, 180 000 €, 60 000 €, 15 000–25 000 €, 3 000 €,
12 000, 23 tickets, 80 %, 5 ans, 4 h…) figurent toutes dans la transcription, et
les six noms propres cités (Kepler, Amélie, Thomas, Karim, Léa, OVH) aussi.

**Structure et lecture.** Titre, phrase d'ouverture qui situe la réunion, points
clés par lot, puis une section décisions/actions nominative. Trois comportements
qui n'allaient pas de soi :

- Le **désaccord** est restitué comme un désaccord — les deux positions sont
  exposées dans les points clés, et l'arbitrage apparaît séparément dans les
  décisions, sans que le résumé prenne parti.
- Le sujet **non tranché** (hébergement) est marqué comme tel, « mis en attente,
  à rouvrir une fois le paiement sécurisé », au lieu d'être présenté comme
  décidé ou d'être omis.
- Les étiquettes `[SPEAKER_XX]` sont **conservées et rapprochées** des prénoms
  prononcés dans la réunion, sans en inventer. La transcription contenait une
  incohérence de diarisation volontaire — `SPEAKER_00` pose une question à Karim
  puis y répond — et le modèle l'a résolue de façon cohérente plutôt que de s'y
  perdre.

**Garde-fou d'entrée**, vérifié aux bornes : 150 000 caractères passent,
150 001 lèvent « Transcription trop longue » sans appeler l'API.

**Ce que ce test ne dit pas.** Un seul appel, un seul texte, une seule langue,
un seul style (`concis`). La variation entre runs est réelle — elle s'est vue
sur deux appels. Et le texte étant écrit par nos soins, la couverture mesurée
est un plafond optimiste par rapport à une vraie transcription Whisper.

### Test 10 — `cli.py`, les quatre sous-commandes en conditions réelles (2026-08-07)

Chaque sous-commande a été lancée pour de vrai, pas seulement en `--help`.

| Commande | Résultat | Durée |
|---|---|---|
| `transcribe test-audio/two_voices_generated.wav` | texte français correct, `output/two_voices_generated.txt` | 4,0 s |
| `transcribe … --diarize --num-speakers 2 --summarize` | 2 locuteurs séparés **puis** résumé enchaîné | 23,4 s |
| `batch <dossier> --summarize` | 2 transcriptions + 2 résumés, 1 échec isolé, `exit 1` | — |
| `youtube 'https://youtu.be/V0oo_Nybo6w' --summarize` | transcription anglaise + résumé français | 19,8 s |
| `summarize output/…NASA….txt --style "en trois puces exactement"` | exactement 3 puces | — |

**L'enchaînement `--diarize --summarize` est le cas qui compte** : il traverse
les deux modules les plus éloignés du toolkit en une commande. Sortie obtenue
sur la fixture 2 voix — `[SPEAKER_01]` puis `[SPEAKER_00]`, conforme au Test 4 —
et le résumé écrit dans `output/two_voices_generated_diarized_summary.txt`, pas
dans `…_summary.txt` : c'est bien la sortie **diarisée** qui a été résumée, et
le nom du fichier le dit.

**Reprise du lot, vérifiée sur trois lancements successifs.** Dossier de test
monté hors dépôt : deux fichiers audio valides, un `.wav` corrompu, un `.txt`.

| # | État de départ | Traités | Sautés | Résumés | Code |
|---|---|---|---|---|---|
| 1 | rien dans `output/` | 2 | 0 | 2 produits | 1 *(fichier corrompu)* |
| 2 | tout est là | 0 | 2 | **2 sautés — aucun appel à l'API** | 1 *(idem)* |
| 3 | un `_summary.txt` supprimé, fichier corrompu retiré | 0 | 2 | 1 seul régénéré | 0 |

Le run 2 dure **2,0 s** et ne coûte rien : c'est ce que vérifie ce test. Le
run 3 vérifie l'autre moitié de la règle — une transcription sautée reste
candidate au résumé, sinon reprendre un lot interrompu ne résumerait que la
partie restante.

**Erreurs et avertissements**, tous vérifiés en vrai :

| Cas | Obtenu |
|---|---|
| `transcribe` fichier absent / extension non gérée | message clair, `exit 1` |
| `batch` dossier introuvable | « Dossier introuvable : … », `exit 1` |
| `summarize` fichier absent | « Fichier introuvable : … », `exit 1` |
| `--num-speakers` sans `--diarize` | « Attention : --num-speakers est ignoré sans --diarize. » |
| `--language` avec `--diarize` | avertissement équivalent (whisperx détecte lui-même) |

**Les modules restent utilisables seuls.** `batch.py`, `youtube.py` et
`summarize.py` ont été relancés directement après refactor : bilan de lot
identique, `youtube.py` affiche désormais aussi le chemin de sortie, aide de
`summarize.py` inchangée.

> ⚠️ **Observation hors périmètre du CLI, mais à noter.** Le test
> `--model claude-haiku-4-5` a bien routé le modèle, mais sur une transcription
> d'**une seule phrase** (75 caractères) Haiku a répondu comme si on
> s'adressait à lui — « je n'ai pas accès à des dossiers externes… » — au lieu
> de résumer. Sonnet, sur un texte aussi court, dit correctement que le texte
> est trop court pour être résumé. Le prompt système de `summarize.py` n'a été
> calibré que sur Sonnet ; `--summary-model` reste donc à utiliser en
> connaissance de cause.

### Test 11 — `app.py`, les trois onglets dans un vrai navigateur (2026-08-07)

L'app a été lancée (`streamlit run app.py`) et pilotée dans Chromium, pas
seulement importée : chaque onglet a été utilisé comme un utilisateur le ferait —
dépôt de fichier, saisie de chemin, clic sur le bouton — et le rendu vérifié sur
capture d'écran.

| Onglet | Scénario | Résultat |
|---|---|---|
| Fichier unique | dépôt de `two_voices_generated.wav` | texte français correct, `output/two_voices_generated.txt`, bouton de téléchargement |
| Dossier (batch) | 3 fichiers audio + 1 `.txt` + 1 `.wav` corrompu | **2 succès / 0 sauté / 1 échec**, le `.txt` ignoré au listage |
| Dossier (batch) | même dossier relancé | **0 / 2 sautés / 1**, la reprise se voit dans le tableau |
| YouTube | `https://youtu.be/V0oo_Nybo6w` (NASA) | transcription anglaise conforme au Test 7 |
| YouTube | la même, case « Résumer » cochée | résumé français affiché **et** écrit dans `output/` |

Durées mesurées de bout en bout du script de pilotage — lancement du navigateur
et chargement de la page compris, donc majorées par rapport au traitement seul :
9,5 s pour l'onglet fichier, 12,0 s pour le lot de 3 fichiers, 14,7 s pour la
vidéo NASA, 21,5 s avec le résumé enchaîné. Aucune exception Streamlit
(`stException`) sur aucun run.

**Le fichier corrompu est le cas qui compte** dans l'onglet lot : le traitement
va au bout, la ligne en échec apparaît dans le tableau avec la bannière ffmpeg
réduite à une ligne par `batch.short_reason()`, et les deux autres fichiers sont
transcrits. C'est le comportement du CLI (Test 5), obtenu sans le réécrire.

**Racine autorisée, vérifiée par contournement** et non par lecture du code :

| Saisie | Obtenu |
|---|---|
| `test-audio/batch_demo` | accepté, lot traité |
| `/etc` | refusé — « Chemin hors de la racine autorisée : /private/etc » |
| `../../../../etc` | refusé, message identique |

Le chemin affiché dans le refus est `/private/etc` et non `/etc` : c'est
`realpath` qui a résolu le lien symbolique de macOS **avant** le test de
confinement. C'est exactement ce qu'on lui demande.

**Cas limites d'interface vérifiés :** bouton « Transcrire » grisé tant qu'aucun
fichier n'est déposé, champ langue grisé dès que « Identifier les locuteurs » est
coché, champ « nombre de locuteurs » grisé dans le cas inverse.

**Ce que ce test ne dit pas.** Les fixtures du lot étaient de petits fichiers
montés pour l'occasion, dans un sous-dossier temporaire de `test-audio/`. La
diarisation n'a **pas** été exercée depuis l'app — le chemin est le même appel
`diarize_file()` qu'en CLI, mais ce n'est pas une vérification. Un seul
navigateur (Chromium), une seule session, aucun test de deux onglets de
navigateur ouverts en même temps sur la même app.

### Environnement de test (vérifié le 2026-08-06)

Mac M5 (`Darwin arm64`) — tout est en place :

| Élément | Statut |
|---|---|
| `venv/` | ✅ Python 3.12.13 |
| `mlx-whisper` | ✅ 0.4.3 (avec `mlx` 0.32.0) |
| `whisperx` | ✅ 3.8.6 |
| `yt-dlp` | ✅ 2026.7.4 |
| `python-dotenv` | ✅ 1.2.2 |
| `ffmpeg` | ✅ 8.1.2 dans le `PATH` |
| `anthropic` | ✅ 0.120.2 |
| `ANTHROPIC_API_KEY` / `.env` | ✅ présente, valide, compte crédité |
| `HF_TOKEN` / `.env` | ✅ présent et valide (token classique, lecture) |
| Accès `pyannote/speaker-diarization-community-1` | ✅ conditions acceptées |

> ⚠️ La section « État d'installation par machine » ci-dessus décrit une machine
> Windows 11 / Python 3.14 : elle est **obsolète** et ne correspond pas à la
> machine de dev actuelle.

> ℹ️ `torchcodec` est cassé dans ce venv : il attend les bibliothèques ffmpeg 4
> à 7 (`libavutil.56` à `.59`) alors que la machine a ffmpeg 8.1.2
> (`libavutil.60`), d'où un avertissement pyannote bruyant au démarrage.
> **Confirmé sans impact** : la VAD pyannote, la détection de langue, l'ASR et
> l'alignement tournent tous normalement. whisperx pré-charge l'audio en mémoire
> et le passe sous forme de waveform, ce qui est exactement le contournement
> documenté par pyannote. Ce n'est pas la cause du blocage de la diarisation.

### Reste à valider

- **Diarisation en conditions réalistes** : la séparation est validée, mais sur
  un cas facile — deux voix de synthèse, très éloignées en hauteur, sans
  chevauchement, avec une seule bascule. Restent non testés : le chevauchement
  de parole, les tours de parole rapprochés, deux voix proches, plus de deux
  locuteurs, et de vraies voix humaines dans du bruit.
- **Détection automatique du nombre de locuteurs** : toujours testée avec
  `--num-speakers` explicite, jamais en laissant pyannote décider seul sur un
  fichier multi-voix.
- Autres extensions : `.m4a`, `.wav`, `.opus` et `.ogg` ont été exécutés ;
  `.mp3` et `.mp4` sont acceptés par le code mais jamais passés dans
  `mlx_whisper`.
- `diarize.py` ne valide pas l'extension du fichier, contrairement à
  `transcribe.py` : un fichier non audio y produira une erreur ffmpeg brute.
- Fichier audio corrompu ou tronqué : remonte aujourd'hui en `RuntimeError`
  brute de `mlx_whisper` avec une stacktrace, au lieu d'un message propre.
- Fichier long (> 30 min) : comportement mémoire et découpage non observés.
- `batch.py` sur un vrai lot : testé sur 3 fichiers courts. Le comportement sur
  plusieurs dizaines de fichiers longs — durée totale, mémoire, rechargement du
  modèle à chaque fichier — n'a pas été observé.
- La reprise de `batch.py` se fie à la **présence** du fichier de sortie, jamais
  à son contenu. Une sortie tronquée par une coupure en pleine écriture serait
  considérée comme complète et sautée au lancement suivant. Ce cas n'a pas été
  provoqué en test ; le contournement est `--force`, ou supprimer le `.txt`.
- `youtube.py` : vidéo réellement privée et vidéo bloquée par région ne sont pas
  testées — impossible d'en provoquer une. Leur détection repose sur des motifs
  de message yt-dlp (`private video`, `not available in your country`) qui n'ont
  jamais été déclenchés pour de vrai.
- `youtube.py` : deux vidéos de même titre produisent le même nom de fichier et
  s'écrasent. Avec la reprise de `batch.py`, la seconde serait même sautée.
- `youtube.py` : testé sur des vidéos d'une minute. Rien n'est connu du
  comportement sur une vidéo d'une heure — durée, mémoire, taille du `.opus`.
- Détection de langue : vérifiée sur du français (5 fixtures) et de l'anglais
  (vidéo NASA). Aucune autre langue testée, et aucun cas de bascule de langue
  *à l'intérieur* d'un même fichier — Whisper ne détecte que sur la première
  fenêtre, un enregistrement bilingue serait donc transcrit dans une seule
  langue.
- `summarize.py` n'a jamais été lancé sur une **vraie** transcription Whisper
  longue : le seul texte de test à l'échelle est écrit à la main (Test 9). Les
  erreurs typiques d'un ASR — noms propres déformés, chiffres mal reconnus — ne
  sont donc pas représentées, alors que ce sont elles qui piègent un résumé.
- `summarize.py` : un seul appel mesuré, un seul style (`concis`), une seule
  langue. La couverture varie d'un run à l'autre — observé sur deux appels.
- `summarize.py` ne découpe pas les entrées : au-delà de 150 000 caractères il
  refuse avec un message clair plutôt que de laisser l'API échouer, mais il n'y
  a pas de chunking. Le plafond `MAX_TOKENS = 4096` en sortie n'a jamais été
  approché (1 237 tokens sur le run le plus gros) et la troncature n'a été
  vérifiée qu'en simulant `stop_reason: max_tokens`.
- `cli.py` : `--summary-model` et `--summary-style` n'ont été exercés que via la
  sous-commande `summarize`, jamais enchaînés derrière `--summarize` sur une
  entrée audio. Le câblage est le même parseur parent pour les trois entrées,
  mais ce n'est pas une vérification.
- `cli.py` : un lot où **le résumé** échoue (clé absente, quota dépassé) n'a pas
  été provoqué. Le code compte les échecs et sort en 1 sans interrompre la
  série, comme pour les transcriptions ; ce chemin n'a pas été exécuté.
- `cli.py` : la reprise des résumés se fie, comme celle des transcriptions, à la
  **présence** du `_summary.txt`, jamais à son contenu.
- `summarize.py` : le prompt système n'est calibré que pour `claude-sonnet-5`.
  Sur `claude-haiku-4-5` et une entrée d'une phrase, le modèle répond à côté
  (Test 10). Aucun autre modèle n'a été essayé.
- `app.py` : la diarisation n'a jamais été lancée depuis l'interface web, ni le
  résumé d'un lot entier (case « Résumer » sur l'onglet dossier). Les deux
  passent par les mêmes appels qu'en CLI, mais le chemin n'a pas été exécuté.
- `app.py` : un traitement long bloque la page jusqu'à la fin — pas de barre de
  progression fichier par fichier, seulement un spinner. Sur un lot de plusieurs
  dizaines de fichiers, rien ne distingue « en cours » de « figé ». La sortie
  détaillée de `process_folder()` part sur stdout, donc dans le terminal, pas
  dans le navigateur.
- `app.py` : `st.session_state` est propre à une session de navigateur. Deux
  onglets ouverts sur la même app ont chacun leur résultat, mais écrivent dans le
  même `output/` — deux traitements simultanés du même fichier n'ont pas été
  provoqués.
- `app.py` : testé sur Chromium uniquement, à une seule taille de fenêtre.
- Le toolkit n'est pas installable (`pip install -e .`) : voir
  [Pourquoi `python src/cli.py`](#pourquoi-python-srcclipy-et-pas-une-commande-whisper-toolkit-installée).
- Autres modèles que `whisper-large-v3-mlx`.
- Tests automatisés dans `tests/` : aucun pour l'instant, tout a été vérifié
  à la main.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
