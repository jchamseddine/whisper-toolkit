# whisper-toolkit

CLI Python de transcription audio **locale**, basé sur Whisper.

> **Statut : en cours de développement.** La transcription locale de base est
> implémentée et testée (voir [Testing Status](#testing-status)). Diarisation,
> batch, YouTube et résumé ne le sont pas encore.

## Fonctionnalités prévues

- **Transcription locale** via [`mlx-whisper`](https://github.com/ml-explore/mlx-examples) (optimisé Apple Silicon)
- **Diarisation** (identification des locuteurs) via [`whisperx`](https://github.com/m-bain/whisperX)
- **Batch** : traitement d'un dossier entier
- **Surveillance de dossier** : transcription automatique des nouveaux fichiers
- **YouTube** : transcription directe depuis une URL via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- **Résumé automatique** de la transcription via l'API Claude
- Le tout dans un **CLI unifié** (`argparse`)

## Structure

```
whisper-toolkit/
├── CLAUDE.md          # guidelines de dev + contexte projet
├── README.md
├── requirements.txt
├── .gitignore
├── venv/              # environnement virtuel (non versionné)
├── src/               # code du CLI
└── tests/             # tests (vide pour l'instant)
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

`ffmpeg` doit être disponible dans le `PATH` (requis par `yt-dlp` et par les
backends Whisper).

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
| └ `transcribe_file()` | ✅ | ✅ | ✅ | `whisper-large-v3-mlx`, `language="fr"`, fichier `.m4a` |
| └ `save_transcript()` | ✅ | ✅ | ✅ | `output/test_fr.txt` créé et relu |
| └ CLI `argparse` | ✅ | ✅ | ✅ | `--help`, run nominal, codes de sortie |
| └ erreur fichier absent | ✅ | ✅ | ✅ | message clair + `exit 1` |
| └ erreur extension | ✅ | ✅ | ✅ | message clair + `exit 1` |
| `src/__init__.py` | ✅ (vide) | ✅ | n/a | simple marqueur de package |
| Diarisation (`whisperx`) | ❌ | — | — | dépendance installée, code non écrit |
| YouTube (`yt-dlp`) | ❌ | — | — | dépendance installée, code non écrit |
| Batch / surveillance dossier | ❌ | — | — | étape ultérieure |
| Résumé (API Claude) | ❌ | — | — | `anthropic` absent de `requirements.txt` |
| `tests/` | ❌ vide | — | — | aucun test automatisé |

### Résultat de la transcription réelle (2026-08-06)

Échantillon généré avec la voix système macOS `Thomas` (fr_FR), 6,3 s, `.m4a` :

| | |
|---|---|
| **Texte attendu** | « Bonjour, ceci est un test de transcription pour le projet whisper toolkit. Il fait beau aujourd'hui à Paris. » |
| **Texte obtenu** | « Bonjour, ceci est un test de transcription pour le projet Wisp et Tolkien. Il fait beau aujourd'hui à Paris. » |

Seul écart : « whisper toolkit » → « Wisp et Tolkien ». C'est un artefact de
l'échantillon, pas du modèle — la voix française prononce ces deux mots anglais
à la française, et Whisper transcrit fidèlement ce qu'il entend. Ponctuation,
accents et apostrophes sont corrects.

**Performance** (Mac M5, `whisper-large-v3-mlx`) :

| Run | Durée | Détail |
|---|---|---|
| 1er | 4 min 16 s | dont 3 min 49 s de téléchargement du modèle (~3 Go) |
| Suivants | 3,6 s | modèle en cache, pour 6,3 s d'audio |

### Environnement de test (vérifié le 2026-08-06)

Mac M5 (`Darwin arm64`) — tout est en place :

| Élément | Statut |
|---|---|
| `venv/` | ✅ Python 3.12.13 |
| `mlx-whisper` | ✅ 0.4.3 (avec `mlx` 0.32.0) |
| `whisperx` | ✅ 3.8.6 |
| `yt-dlp` | ✅ 2026.7.4 |
| `python-dotenv` | ✅ 1.2.2 |
| `ffmpeg` | ✅ présent dans le `PATH` |
| `anthropic` | ❌ non installé, pas encore requis |

> ⚠️ La section « État d'installation par machine » ci-dessus décrit une machine
> Windows 11 / Python 3.14 : elle est **obsolète** et ne correspond pas à la
> machine de dev actuelle.

### Reste à valider

- Autres extensions : seul `.m4a` a été exécuté ; `.mp3`, `.wav`, `.mp4` sont
  acceptés par le code mais jamais passés dans `mlx_whisper`.
- Vrai enregistrement humain (voix, bruit de fond) plutôt qu'un échantillon TTS.
- Fichier long (> 30 min) : comportement mémoire et découpage non observés.
- Autres langues et autres modèles que les valeurs par défaut.
- Tests automatisés dans `tests/` : aucun pour l'instant, tout a été vérifié
  à la main.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
