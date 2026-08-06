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
Whisper. Projet personnel (side project), en cours de développement.

Fonctionnalités prévues :
- Transcription locale via **mlx-whisper** (optimisé Apple Silicon)
- Diarisation (identification des locuteurs) via **whisperx**
- Support **batch** (dossier entier) et **surveillance de dossier**
- Transcription depuis une **URL YouTube** via **yt-dlp**
- **Résumé automatique** via l'API Claude
- Le tout exposé via un **CLI unifié** avec `argparse`

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
├── venv/              # environnement virtuel (non versionné)
├── src/               # code du CLI
└── tests/             # tests (vide pour l'instant)
```

## Contraintes de plateforme

`mlx-whisper` ne s'installe **que sur macOS Apple Silicon**. Le développement
peut se faire sur une autre machine, mais l'import de `mlx_whisper` doit rester
optionnel / paresseux (lazy import) pour que le reste du CLI fonctionne
ailleurs. Voir le README pour l'état d'installation de la machine courante.

## État d'avancement

Le projet est découpé en étapes. **Étape 1 terminée** : setup de l'environnement
et structure du projet. La logique de transcription arrive à l'étape 3 — ne pas
l'implémenter avant.
