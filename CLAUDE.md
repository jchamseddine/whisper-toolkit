# CLAUDE.md

Guidelines de comportement pour tout développement futur sur ce repo.

## Principes de travail

### Think Before Coding
Réfléchir avant d'écrire du code. Comprendre le problème, lire le code existant,
identifier les fichiers concernés — puis coder. Pas de code jetable, pas de
prototype qu'on jette ensuite : ce qui est écrit est destiné à rester.

### Simplicity First
Privilégier la solution la plus simple qui marche. Pas d'abstraction anticipée,
pas de couche de configuration pour un cas unique, pas de design pattern là où
une fonction suffit. Une dépendance de plus doit être justifiée.

### Surgical Changes
Modifications ciblées et minimales. Pas de refactor non demandé, pas de
reformatage de fichiers qu'on ne touche pas, pas de renommage opportuniste.
Si un refactor semble nécessaire, le proposer — ne pas le faire au passage.

### Goal-Driven Execution
Rester focus sur l'objectif de la tâche en cours. Ne pas déborder sur les étapes
suivantes du projet. Si une idée sort du périmètre, la noter et continuer.

## Contexte du projet

`whisper-toolkit` — un CLI Python de transcription audio **locale**, basé sur
Whisper. Projet personnel (side project).

Fonctionnalités, toutes implémentées et exécutées pour de vrai :
- Transcription locale via **mlx-whisper** (optimisé Apple Silicon)
- Diarisation (identification des locuteurs) via **whisperx**
- Traitement **batch** d'un dossier entier, avec reprise
- Transcription depuis une **URL YouTube** via **yt-dlp**
- **Résumé automatique** via l'API Claude
- Le tout derrière un **CLI unifié** `argparse` (`python src/cli.py`)

**La surveillance de dossier est volontairement écartée.** Le traitement par lot
couvre l'usage réel ; le mode watchdog ne sera ajouté que si le besoin se
confirme.

## Stack technique

| Usage | Outil |
|---|---|
| Langage | Python 3 (venv local, dossier `venv/`) |
| Transcription | `mlx-whisper` (Apple Silicon uniquement) |
| Diarisation | `whisperx` |
| Téléchargement audio | `yt-dlp` |
| Résumé | API Claude (`anthropic`) |
| CLI | `argparse` (stdlib) |

## Structure de dossiers

```
whisper-toolkit/
├── CLAUDE.md          # ce fichier
├── README.md
├── requirements.txt
├── .gitignore
├── .env               # HF_TOKEN + ANTHROPIC_API_KEY (non versionné)
├── venv/              # environnement virtuel (non versionné)
├── output/            # transcriptions produites (non versionné)
├── src/
│   ├── cli.py         # CLI unifié — point d'entrée
│   ├── transcribe.py  # transcription simple (mlx-whisper)
│   ├── diarize.py     # transcription + locuteurs (whisperx)
│   ├── batch.py       # traitement d'un dossier entier
│   ├── youtube.py     # transcription depuis une URL (yt-dlp)
│   └── summarize.py   # résumé d'une transcription (API Claude)
└── tests/             # tests (vide pour l'instant)
```

## Contraintes de plateforme

`mlx-whisper` ne s'installe **que sur macOS Apple Silicon**. Le développement
peut se faire sur une autre machine, mais l'import de `mlx_whisper` doit rester
optionnel / paresseux (lazy import) pour que le reste du CLI fonctionne
ailleurs. Voir le README pour l'état d'installation de la machine courante.

## État actuel

**Les 8 étapes du plan initial sont terminées**, chacune validée par des
exécutions réelles — mesures et cas limites dans le README, section
*Testing Status*. Il n'y a plus d'étape « à ne pas anticiper » : le prochain
travail est du durcissement, des tests automatisés, ou une fonctionnalité
nouvelle à définir.

### Deux couches, à ne pas mélanger

**Couche pipeline** — le travail audio réel. Ces deux modules sont indépendants :
ni import croisé, ni état partagé, ni backend commun. Ce n'est pas un accident,
chacun est le meilleur outil pour son usage.

| Module | Rôle | Backend |
|---|---|---|
| `transcribe.py` | audio → texte | `mlx-whisper`, GPU Metal |
| `diarize.py` | audio → segments `{start, end, text, speaker}` | `whisperx` → faster-whisper, **CPU uniquement** |

**Couche orchestration** — aucune logique audio, uniquement de la délégation.

| Module | Rôle |
|---|---|
| `batch.py` | liste un dossier, délègue fichier par fichier, reprise par défaut |
| `youtube.py` | télécharge l'audio (yt-dlp), puis délègue |
| `summarize.py` | texte → résumé via l'API Claude — seul module qui sorte de la machine, et seul qui coûte de l'argent |
| `cli.py` | point d'entrée : une commande, quatre sous-commandes |

### Comment ça s'assemble

```
cli.py transcribe FICHIER ──> transcribe_file() | diarize_file()
cli.py batch DOSSIER      ──> process_folder()      ──> idem, fichier par fichier
cli.py youtube URL        ──> transcribe_youtube()  ──> idem, après téléchargement
cli.py summarize F.txt    ──> summarize_text()
                                   ▲
                 --summarize enchaîne cette étape sur la sortie des trois autres
```

Les règles qui tiennent l'ensemble — les enfreindre casse des choses qui
marchent aujourd'hui :

- **`cli.py` ne contient aucune logique métier.** Il appelle, il affiche. Une
  fonctionnalité nouvelle va dans le module concerné, jamais ici.
- **Les conventions de nommage des sorties appartiennent aux modules qui
  écrivent.** `transcript_path()`, `diarized_transcript_path()` et
  `summary_path()` en sont la source unique — ne jamais reconstruire un chemin
  de sortie ailleurs, c'est ce qui garde la reprise de `batch.py` cohérente.
- **Les imports entre modules de `src/` sont plats** (`from transcribe import …`)
  parce que ces fichiers s'exécutent comme des scripts. Un `python -m src.cli`
  ne fonctionnerait pas sans imports relatifs.
- **Les dépendances lourdes s'importent paresseusement** : `mlx_whisper`,
  `whisperx` et `anthropic` dans les fonctions qui les utilisent, les modules
  frères dans les handlers de `cli.py`. C'est ce qui garde `--help` à 0,03 s et
  le reste du toolkit utilisable hors Apple Silicon.
- **Chaque module garde son propre `main()`** et reste lançable seul
  (`python src/diarize.py fichier.wav`). C'est là que vivent les réglages rares
  — `--model`, `--diarization-model` — que le CLI unifié n'expose pas
  volontairement.
- **La langue n'est jamais forcée par défaut.** Forcer une langue qui n'est pas
  celle de l'audio ne produit pas une erreur mais une traduction inventée,
  fluide et indétectable dans la sortie.

### Ce qui n'est pas fait

- Surveillance de dossier — volontairement écartée (voir plus haut).
- `tests/` est vide : aucun test automatisé, tout a été vérifié à la main.
- Le toolkit n'est pas installable (`pip install -e .`) ; la raison est
  documentée dans le README, section *Usage*.
- Les réserves connues (diarisation testée sur voix de synthèse seulement,
  résumé jamais mesuré sur une vraie transcription longue, etc.) sont listées
  dans le README sous *Reste à valider* — à lire avant de promettre quoi que ce
  soit sur ces points.
