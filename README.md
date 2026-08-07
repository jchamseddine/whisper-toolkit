# whisper-toolkit

CLI Python de transcription audio **locale**, basé sur Whisper.

> **Statut : en cours de développement.** Transcription locale, diarisation et
> traitement par lot sont implémentés et validés — la séparation des locuteurs
> reste toutefois testée sur des voix de synthèse, sans chevauchement de parole.
> YouTube et résumé ne sont pas commencés. Détail dans
> [Testing Status](#testing-status).

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
├── .nltk_data/        # cache NLTK local au projet (non versionné, régénérable)
├── venv/              # environnement virtuel (non versionné)
├── test-audio/        # échantillons de test (ignoré, sauf la fixture synthétique)
├── output/            # transcriptions produites (non versionné)
├── src/
│   ├── transcribe.py  # transcription simple (mlx-whisper)
│   ├── diarize.py     # transcription + locuteurs (whisperx)
│   ├── batch.py       # traitement d'un dossier entier
│   └── youtube.py     # transcription depuis une URL (yt-dlp)
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

**Langue : détection automatique, contrairement au reste du toolkit.**
`transcribe.py` force `fr` par défaut, ce qui convient à des enregistrements
personnels mais pas à YouTube. `youtube.py` passe donc `language=None` et laisse
Whisper détecter ; `--language` force au besoin. Sans ça, une vidéo anglaise
ressort en français inventé — voir le Test 7, où le cas s'est produit.

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
| `src/batch.py` | ✅ | ✅ | ✅ | validé le 2026-08-07 |
| └ `list_audio_files()` | ✅ | ✅ | ✅ | filtre extensions, ignore `.txt` et sous-dossiers |
| └ `process_folder()` | ✅ | ✅ | ✅ | mode transcription et mode `--diarize` |
| └ échec partiel | ✅ | ✅ | ✅ | **le lot continue**, 2/3 traités sur fichier corrompu |
| └ `--num-speakers` propagé | ✅ | ✅ | ✅ | borne `[2, 2]` bien reçue par pyannote |
| └ `_short_reason()` | ✅ | ✅ | ✅ | bannière ffmpeg de 13 lignes réduite à 1 |
| └ dossier introuvable / vide | ✅ | ✅ | ✅ | `exit 1` / `exit 0` avec message |
| `src/__init__.py` | ✅ (vide) | ✅ | n/a | simple marqueur de package |
| YouTube (`yt-dlp`) | ❌ | — | — | dépendance installée, code non écrit |
| Surveillance de dossier | ❌ | — | — | volontairement non implémentée |
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
> 1173 caractères**, ce qui noyait tout le résumé du lot. `_short_reason()` la
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
> L'audio est anglais, mais `transcribe.py` force `language="fr"` : Whisper a
> rendu un texte français inventé, fluide et plausible, qui n'avait qu'un
> rapport lointain avec l'original. Rien dans la sortie ne signalait le
> problème. C'est ce qui a motivé le passage en détection automatique dans
> `youtube.py`. Après correction, la transcription correspond aux sous-titres
> YouTube (123 mots contre 121 de référence).

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
- Autres langues et autres modèles que les valeurs par défaut.
- Tests automatisés dans `tests/` : aucun pour l'instant, tout a été vérifié
  à la main.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
