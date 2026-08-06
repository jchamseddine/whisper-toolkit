# whisper-toolkit

CLI Python de transcription audio **locale**, basé sur Whisper.

> **Statut : en cours de développement.** Transcription locale et diarisation
> sont implémentées et validées, séparation de deux locuteurs comprise — mais
> sur des voix de synthèse, sans chevauchement de parole. Batch, YouTube et
> résumé ne sont pas commencés. Détail dans [Testing Status](#testing-status).

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
├── .env               # HF_TOKEN pour la diarisation (non versionné)
├── venv/              # environnement virtuel (non versionné)
├── test-audio/        # échantillons de test (ignoré, sauf la fixture synthétique)
├── output/            # transcriptions produites (non versionné)
├── src/
│   ├── transcribe.py  # transcription simple (mlx-whisper)
│   └── diarize.py     # transcription + locuteurs (whisperx)
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
| └ `transcribe_file()` | ✅ | ✅ | ✅ | `whisper-large-v3-mlx`, `language="fr"`, `.m4a` `.wav` `.opus` `.ogg` |
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
| `src/__init__.py` | ✅ (vide) | ✅ | n/a | simple marqueur de package |
| YouTube (`yt-dlp`) | ❌ | — | — | dépendance installée, code non écrit |
| Batch / surveillance dossier | ❌ | — | — | étape ultérieure |
| Résumé (API Claude) | ❌ | — | — | `anthropic` absent de `requirements.txt` |
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
| `anthropic` | ❌ non installé, pas encore requis |
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
- Autres langues et autres modèles que les valeurs par défaut.
- Tests automatisés dans `tests/` : aucun pour l'instant, tout a été vérifié
  à la main.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
