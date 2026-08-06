# whisper-toolkit

CLI Python de transcription audio **locale**, basé sur Whisper.

> **Statut : en cours de développement.** Étape 1 (setup de l'environnement et
> structure du projet) terminée. La logique de transcription n'est pas encore
> implémentée.

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

Suivi de ce qui est **écrit** vs ce qui est **réellement validé**, pour savoir
exactement quoi vérifier une fois l'environnement complet en place. À mettre à
jour à chaque étape.

| Module | Écrit | Compile | Testé à l'exécution | Notes |
|---|---|---|---|---|
| `src/__init__.py` | ✅ (vide) | ✅ | n/a | simple marqueur de package |
| `src/transcribe.py` | ❌ **pas encore créé** | — | — | prévu à l'étape 3 |
| CLI `argparse` | ❌ | — | — | étape ultérieure |
| Diarisation (`whisperx`) | ❌ | — | — | étape ultérieure |
| YouTube (`yt-dlp`) | ❌ | — | — | étape ultérieure |
| Résumé (API Claude) | ❌ | — | — | étape ultérieure |
| `tests/` | ❌ vide | — | — | aucun test écrit |

**Aucun code de transcription n'a encore été écrit** : il n'y a donc, à ce jour,
rien à compiler ni à exécuter. Le tableau existe pour être rempli au fur et à
mesure, pas pour documenter une dette de tests.

### État de la machine de dev (vérifié le 2026-08-06)

La machine courante est bien un **macOS Apple Silicon (`arm64`)**, mais
l'environnement n'y est pas encore installé — aucun test réel n'est possible
en l'état :

| Élément | Statut |
|---|---|
| `venv/` | ❌ absent |
| Python disponible | 3.14.6 (Homebrew) — trop récent pour `whisperx` |
| `mlx-whisper` | ❌ non installé |
| `whisperx` | ❌ non installé |
| `yt-dlp` | ❌ non installé |
| `anthropic` | ❌ non installé (et pas encore dans `requirements.txt`) |
| `ffmpeg` | ❌ absent du `PATH` |

> ⚠️ La section « État d'installation par machine » ci-dessus décrit une machine
> Windows 11 / Python 3.14 ; elle ne correspond plus à la machine sur laquelle
> ce dépôt est actuellement ouvert.

### À valider une fois l'environnement en place

1. Créer le `venv` avec **Python 3.12 ou 3.13** (3.14 casse `whisperx`, cf.
   ci-dessus) — aucun des deux n'est installé sur cette machine pour l'instant.
2. `pip install -r requirements.txt` → vérifier que `mlx-whisper` s'installe
   effectivement (marqueur d'environnement satisfait sur Apple Silicon).
3. Installer `ffmpeg` et vérifier sa présence dans le `PATH`.
4. `python -m py_compile src/*.py` sur les modules une fois écrits.
5. Vérifier que `import mlx_whisper` fonctionne, puis lancer une transcription
   réelle sur un fichier audio court.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
