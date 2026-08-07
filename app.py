"""Interface web Streamlit, en plus du CLI — pas à sa place.

Pendant exact de `cli.py` : aucune logique de transcription, de diarisation, de
téléchargement ni de résumé n'est écrite ici. Chaque onglet appelle les
fonctions des modules qui les portent, puis affiche ce qu'elles ont produit. Les
deux points d'entrée partagent donc le même code métier, et les sorties
atterrissent au même endroit (`output/`), sous les mêmes noms.

Une exception assumée : l'onglet « Dictée rapide », qui n'existe pas côté CLI et
n'écrit rien — ni l'audio, ni le texte, sauf demande explicite. Voir
`_transcribe_recording()`.

Lancement : `streamlit run app.py` depuis la racine du dépôt.
"""

import hashlib
import os
import sys
import tempfile
from datetime import datetime

# `python src/cli.py` place `src/` en tête de `sys.path`, ce qui fait marcher les
# imports plats (`from transcribe import …`) des modules du toolkit.
# `streamlit run app.py` y place la racine du dépôt à la place : sans cet ajout,
# aucun module de `src/` n'est importable.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import streamlit as st  # noqa: E402  -- doit suivre l'ajout de src/ à sys.path

# Même règle qu'en tête de `cli.py` : seuls les imports gratuits sont faits ici.
# `transcribe` ne coûte rien (mlx_whisper est paresseux) et sa constante sert dès
# la construction de l'uploader. Tout le reste — `diarize`, `batch`, `youtube`,
# `summarize` — est importé dans les fonctions qui s'en servent, sinon chaque
# rerun de Streamlit paierait nltk et yt-dlp pour afficher trois onglets.
from ffmpeg_path import ensure_on_path  # noqa: E402
from transcribe import SUPPORTED_EXTENSIONS  # noqa: E402

# Racine autorisée pour le champ « dossier » de l'onglet batch. Ce champ accepte
# un chemin tapé à la main : sans borne, il suffirait d'exposer l'app sur le
# réseau pour laisser n'importe qui lister et transcrire n'importe quel dossier
# de la machine. L'usage prévu est local, mais le garde-fou est posé maintenant
# plutôt qu'après. `WHISPER_TOOLKIT_ROOT` permet d'élargir la racine en
# connaissance de cause (ex. `~/Documents/cours`).
BROWSE_ROOT = os.path.realpath(os.environ.get("WHISPER_TOOLKIT_ROOT", PROJECT_ROOT))

LANGUAGE_HELP = (
    "À laisser sur « Détection automatique » sauf besoin précis : forcer une "
    "langue qui n'est pas celle de l'audio ne produit pas une erreur mais une "
    "traduction inventée, fluide et indétectable dans la sortie. "
    "Tape pour filtrer la liste."
)

# Langues du sélecteur, code Whisper en valeur. `None` laisse la détection
# automatique, qui reste le défaut partout dans le toolkit.
#
# C'est un sous-ensemble courant, pas les 100 langues que Whisper connaît. La
# liste complète n'est lisible que dans `mlx_whisper.tokenizer.LANGUAGES`, qui
# ne s'installe que sur Apple Silicon : la tirer de là rendrait l'app
# inaffichable ailleurs — et coûterait 0,8 s au démarrage — pour un menu
# déroulant. Ajouter une langue ici tient en une ligne, et le CLI reste ouvert à
# n'importe quel code Whisper via `--language`.
#
# Les codes ont été vérifiés un à un contre `mlx_whisper.tokenizer.LANGUAGES`.
LANGUAGES: dict[str, str | None] = {
    "Détection automatique": None,
    "Français": "fr",
    "Anglais": "en",
    "Espagnol": "es",
    "Allemand": "de",
    "Italien": "it",
    "Portugais": "pt",
    "Néerlandais": "nl",
    "Arabe": "ar",
    "Catalan": "ca",
    "Chinois": "zh",
    "Coréen": "ko",
    "Danois": "da",
    "Finnois": "fi",
    "Grec": "el",
    "Hébreu": "he",
    "Hindi": "hi",
    "Hongrois": "hu",
    "Indonésien": "id",
    "Japonais": "ja",
    "Norvégien": "no",
    "Polonais": "pl",
    "Roumain": "ro",
    "Russe": "ru",
    "Suédois": "sv",
    "Tchèque": "cs",
    "Thaï": "th",
    "Turc": "tr",
    "Ukrainien": "uk",
    "Vietnamien": "vi",
}


def _resolve_browse_path(raw: str) -> str:
    """Résout un chemin saisi et refuse tout ce qui sort de `BROWSE_ROOT`.

    Les chemins relatifs partent de la racine autorisée ; un chemin absolu est
    gardé tel quel par `os.path.join`, puis rejeté par le test de confinement.
    `realpath` est indispensable : il résout `..` et les liens symboliques, donc
    un lien posé dans le dépôt ne peut pas servir de passerelle vers `/`.
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("Indique un dossier à traiter.")

    resolved = os.path.realpath(
        os.path.join(BROWSE_ROOT, os.path.expanduser(candidate))
    )
    if resolved != BROWSE_ROOT and not resolved.startswith(BROWSE_ROOT + os.sep):
        raise ValueError(
            f"Chemin hors de la racine autorisée : {resolved}\n"
            f"Seul {BROWSE_ROOT} et ses sous-dossiers sont accessibles. "
            f"Définis WHISPER_TOOLKIT_ROOT avant de lancer l'app pour l'élargir."
        )

    return resolved


def _save_upload(uploaded, directory: str) -> str:
    """Écrit le fichier reçu dans `directory` et retourne son chemin.

    Le nom vient du navigateur, donc de l'extérieur : il est réduit à son
    basename, sinon un nom comme `../../x.wav` ferait écrire hors du dossier
    temporaire. Il est conservé par ailleurs, parce que c'est lui qui donne son
    nom à la sortie (`output/{nom}.txt`) — exactement comme en CLI.
    """
    name = os.path.basename(uploaded.name.replace("\\", "/"))
    if not name or name in {".", ".."}:
        raise ValueError(f"Nom de fichier inexploitable : {uploaded.name!r}")

    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(uploaded.getbuffer())

    return path


def _audio_options(prefix: str) -> dict:
    """Affiche le jeu d'options commun aux trois onglets et retourne les valeurs.

    Pendant du parseur parent `audio` de `cli.py` : les options sont déclarées
    une seule fois, pas trois. `prefix` sépare les clés de widgets, que Streamlit
    veut uniques dans toute l'app.
    """
    left, right = st.columns(2)

    with left:
        diarize = st.checkbox(
            "Identifier les locuteurs",
            key=f"{prefix}_diarize",
            help="Passe par whisperx au lieu de mlx-whisper. Tourne sur CPU : "
            "comptez plusieurs fois la durée de l'audio.",
        )
        num_speakers = st.number_input(
            "Nombre de locuteurs, si connu",
            min_value=1,
            max_value=20,
            value=None,
            step=1,
            key=f"{prefix}_num_speakers",
            disabled=not diarize,
            placeholder="détection automatique",
        )

    with right:
        summarize = st.checkbox(
            "Résumer via l'API Claude",
            key=f"{prefix}_summarize",
            help="Seule option payante, et seule étape qui sorte de la machine : "
            "le texte est envoyé à l'API Claude.",
        )
        # Un sélecteur et non un champ libre : une valeur inventée ne serait pas
        # rejetée par Whisper, elle produirait une traduction. Le champ est grisé
        # en diarisation, où whisperx détecte la langue de son côté — c'est
        # l'équivalent natif de l'avertissement que le CLI imprime.
        language_label = st.selectbox(
            "Langue",
            options=list(LANGUAGES),
            index=0,
            key=f"{prefix}_language",
            disabled=diarize,
            help=LANGUAGE_HELP,
        )

    return {
        "diarize": diarize,
        "num_speakers": int(num_speakers) if num_speakers else None,
        "language": LANGUAGES[language_label],
        "summarize": summarize,
    }


def _result_from_output(output_path: str, options: dict) -> dict:
    """Relit la sortie écrite et, si demandé, enchaîne le résumé.

    La transcription est relue depuis le disque plutôt que remise en forme ici,
    pour la même raison que dans `cli.py` : le format `[SPEAKER_XX] texte` n'a
    qu'une définition, dans `diarize.py`.

    Un résumé en échec n'efface pas la transcription, qui est déjà écrite : il
    est rapporté à part.
    """
    with open(output_path, encoding="utf-8") as f:
        text = f.read()

    result = {
        "path": output_path,
        "text": text,
        "summary": None,
        "summary_path": None,
        "summary_error": None,
    }

    if options["summarize"]:
        from summarize import save_summary, summarize_text

        try:
            with st.spinner("Résumé via l'API Claude…"):
                summary = summarize_text(text)
        except ValueError as error:
            result["summary_error"] = str(error)
        else:
            result["summary"] = summary
            result["summary_path"] = save_summary(summary, output_path)

    return result


def _transcribe_one(audio_path: str, options: dict) -> dict:
    """Transcrit un fichier déjà posé sur le disque, avec ou sans locuteurs."""
    label = os.path.basename(audio_path)

    if options["diarize"]:
        from diarize import diarize_file, save_diarized_transcript

        with st.spinner(f"Diarisation de {label}… (CPU, comptez large)"):
            segments = diarize_file(audio_path, num_speakers=options["num_speakers"])
            output_path = save_diarized_transcript(segments, audio_path)
    else:
        from transcribe import save_transcript, transcribe_file

        with st.spinner(f"Transcription de {label}…"):
            text = transcribe_file(audio_path, language=options["language"])
            output_path = save_transcript(text, audio_path)

    return _result_from_output(output_path, options)


def _render_result(key: str) -> None:
    """Affiche la transcription mémorisée pour un onglet, et son résumé."""
    result = st.session_state.get(key)
    if not result:
        return

    st.success(f"Transcription enregistrée : {result['path']}")
    st.text_area("Transcription", result["text"], height=280, key=f"{key}_text_area")
    st.download_button(
        "Télécharger le .txt",
        data=result["text"],
        file_name=os.path.basename(result["path"]),
        mime="text/plain",
        key=f"{key}_download",
    )

    if result["summary_error"]:
        st.error(result["summary_error"])
    elif result["summary"]:
        st.divider()
        st.markdown("#### Résumé")
        st.markdown(result["summary"])
        st.caption(f"Résumé enregistré : {result['summary_path']}")
        st.download_button(
            "Télécharger le résumé",
            data=result["summary"],
            file_name=os.path.basename(result["summary_path"]),
            mime="text/plain",
            key=f"{key}_summary_download",
        )


def _tab_single() -> None:
    uploaded = st.file_uploader(
        "Fichier audio",
        type=[extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS],
        key="single_upload",
    )
    options = _audio_options("single")

    if st.button(
        "Transcrire", key="single_run", type="primary", disabled=uploaded is None
    ):
        # Le fichier reçu ne sert qu'à alimenter le pipeline : il est écrit dans
        # un dossier temporaire, effacé à la sortie du bloc. Seule la
        # transcription, dans `output/`, survit.
        with tempfile.TemporaryDirectory() as workdir:
            try:
                audio_path = _save_upload(uploaded, workdir)
                st.session_state["single"] = _transcribe_one(audio_path, options)
            except (FileNotFoundError, ValueError) as error:
                st.session_state["single"] = None
                st.error(str(error))

    _render_result("single")


def _run_folder(folder: str, options: dict, force: bool) -> dict:
    """Traite un dossier, puis en résume les transcriptions si demandé."""
    from batch import process_folder

    with st.spinner(f"Traitement de {folder}…"):
        summary = process_folder(
            folder,
            diarize=options["diarize"],
            num_speakers=options["num_speakers"],
            force=force,
            language=options["language"],
        )

    summaries_failed = None
    if options["summarize"] and (summary["success"] or summary["skipped"]):
        # La règle de résumé d'un lot — résumer aussi les fichiers sautés par la
        # reprise, mais pas ceux dont le `_summary.txt` existe déjà — vit dans
        # `cli.summarize_batch()`. On l'appelle plutôt que de la réécrire ici :
        # dupliquée, elle finirait par diverger de celle du CLI.
        from cli import summarize_batch

        with st.spinner("Résumés via l'API Claude…"):
            summaries_failed = summarize_batch(
                summary, diarize=options["diarize"], force=force
            )

    return {"summary": summary, "summaries_failed": summaries_failed}


def _render_batch() -> None:
    """Affiche le bilan d'un lot sous forme de compteurs et de tableau.

    `batch.report_summary()` produit le même bilan sur stdout : c'est le rendu
    qui diffère, pas ce qui est rapporté.
    """
    state = st.session_state.get("batch")
    if not state:
        return

    from batch import short_reason

    summary = state["summary"]
    success, skipped, failed = (
        summary["success"],
        summary["skipped"],
        summary["failed"],
    )

    if not (success or skipped or failed):
        st.info("Aucun fichier audio dans ce dossier.")
        return

    columns = st.columns(3)
    columns[0].metric("Succès", len(success))
    columns[1].metric("Sautés", len(skipped))
    columns[2].metric("Échecs", len(failed))

    rows = [
        {"Fichier": os.path.basename(path), "Statut": "✅ Succès", "Détail": ""}
        for path in success
    ]
    rows += [
        {
            "Fichier": os.path.basename(path),
            "Statut": "⏭️ Sauté",
            "Détail": "déjà traité — cocher « Retraiter » pour le refaire",
        }
        for path in skipped
    ]
    rows += [
        {
            "Fichier": os.path.basename(path),
            "Statut": "❌ Échec",
            "Détail": short_reason(reason),
        }
        for path, reason in failed
    ]
    st.dataframe(rows, hide_index=True)

    if failed:
        st.error(f"{len(failed)} fichier(s) en échec — le lot est allé au bout.")
    else:
        st.success("Lot terminé sans échec.")

    summaries_failed = state["summaries_failed"]
    if summaries_failed:
        st.error(f"{summaries_failed} résumé(s) en échec.")
    elif summaries_failed == 0:
        st.success("Résumés écrits dans output/, à côté des transcriptions.")


def _tab_batch() -> None:
    folder_input = st.text_input(
        "Dossier à traiter",
        value="test-audio",
        key="batch_path",
        help=f"Chemin relatif à {BROWSE_ROOT}, ou absolu sous cette racine.",
    )
    st.caption(
        f"Racine autorisée : `{BROWSE_ROOT}` — un chemin qui en sort est refusé."
    )

    options = _audio_options("batch")
    force = st.checkbox(
        "Retraiter les fichiers déjà traités",
        key="batch_force",
        help="Sans cette case, un fichier dont la sortie existe déjà est sauté : "
        "c'est ce qui permet de relancer un lot interrompu sans tout refaire.",
    )

    if st.button("Lancer le lot", key="batch_run", type="primary"):
        try:
            folder = _resolve_browse_path(folder_input)
            st.session_state["batch"] = _run_folder(folder, options, force)
        except (NotADirectoryError, ValueError) as error:
            st.session_state["batch"] = None
            st.error(str(error))

    _render_batch()


def _transcribe_recording(data: bytes, language: str | None) -> dict:
    """Transcrit un enregistrement en mémoire, sans jamais le poser dans le dépôt.

    L'audio dicté est du brouillon : il n'a pas à survivre à sa transcription, ni
    à rejoindre `test-audio/` ou `output/` avec les fichiers qu'on garde. Il ne
    touche donc le disque que dans le dossier temporaire du système, et le
    `finally` l'y efface — succès, échec ou exception imprévue. Rien n'est laissé
    au ramasse-miettes, qui ne promet ni le moment ni le fait de passer.

    `transcribe_file()` demande un chemin parce que mlx-whisper décode le fichier
    lui-même, en appelant ffmpeg : ce détour par le disque n'est pas évitable.
    """
    from transcribe import transcribe_file

    path = None
    try:
        # `delete=False` parce que le fichier doit rester lisible après la
        # fermeture du handle, le temps que ffmpeg le décode.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(data)
            path = handle.name

        with st.spinner("Transcription de la dictée…"):
            text = transcribe_file(path, language=language)
    except (FileNotFoundError, ValueError) as error:
        return {"text": None, "error": str(error), "path": None}
    finally:
        if path:
            os.unlink(path)

    return {"text": text.strip(), "error": None, "path": None}


def _reset_dictation() -> None:
    """Repart d'un widget vierge, sans garder l'enregistrement précédent.

    Passée en `on_click`, cette fonction s'exécute *avant* la réexécution du
    script : les clés sont donc effacées pendant qu'aucun widget n'est
    instancié, ce qu'une suppression en plein rendu ne permettrait pas.

    L'audio du tour précédent est retiré de `session_state` explicitement.
    Incrémenter le compteur suffirait à afficher un widget neuf, mais les octets
    de la dictée resteraient en mémoire jusqu'à la fin de la session — pour un
    onglet dont l'engagement est de ne rien garder, ce serait un oubli.
    """
    tour = st.session_state.get("dictation_round", 0)
    st.session_state.pop(f"dictation_input_{tour}", None)
    st.session_state.pop(f"dictation_save_{tour}", None)
    st.session_state.pop("dictation", None)
    st.session_state["dictation_round"] = tour + 1


def _tab_dictation() -> None:
    """Dicter au micro et récupérer le texte, sans rien laisser derrière.

    Pas de diarisation ici : on dicte seul. Pas de sauvegarde non plus par
    défaut — l'usage visé est de copier le texte ailleurs dans la seconde, et
    écrire un fichier à chaque essai encombrerait `output/` pour rien.
    """
    st.caption(
        "Dictée mono-locuteur : l'audio n'est ni conservé ni enregistré dans le "
        "dépôt, et le texte n'est sauvegardé que si tu le demandes."
    )

    language_label = st.selectbox(
        "Langue",
        options=list(LANGUAGES),
        index=0,
        key="dictation_language",
        help=LANGUAGE_HELP,
    )
    language = LANGUAGES[language_label]

    # La clé du widget porte un numéro de tour, parce que Streamlit n'offre aucun
    # moyen de vider un `audio_input` en place : sans clé neuve, il garderait son
    # enregistrement et l'onglet resterait bloqué sur la première dictée. Changer
    # la clé lui fait construire un widget vierge — c'est le geste de
    # « Nouvelle dictée ».
    tour = st.session_state.setdefault("dictation_round", 0)
    recording = st.audio_input("Enregistrement", key=f"dictation_input_{tour}")
    if recording is None:
        # Enregistrement supprimé par l'utilisateur : le texte qui l'accompagnait
        # n'a plus de sujet.
        st.session_state.pop("dictation", None)
        return

    data = recording.getvalue()

    # Streamlit réexécute tout le script au moindre clic — cocher la case de
    # sauvegarde suffirait à relancer une transcription. On ne retranscrit donc
    # que si l'audio ou la langue ont changé, la langue en faisant partie parce
    # qu'en changer est une demande explicite de refaire la passe.
    signature = (hashlib.sha1(data).hexdigest(), language)
    state = st.session_state.get("dictation")
    if not state or state["signature"] != signature:
        state = _transcribe_recording(data, language)
        state["signature"] = signature
        st.session_state["dictation"] = state

    if state["error"]:
        st.error(state["error"])
    elif not state["text"]:
        st.warning("Rien n'a été transcrit — enregistrement vide ou inaudible.")
    else:
        # `st.code` plutôt qu'un `text_area` : il porte un bouton « copier »
        # natif, qui est le geste attendu ici.
        st.code(state["text"], language=None, wrap_lines=True)

        if st.checkbox(
            "Sauvegarder quand même dans output/",
            key=f"dictation_save_{tour}",
            help="Décoché, rien n'est écrit : la dictée ne vit que dans cet écran.",
        ):
            if not state["path"]:
                from transcribe import save_transcript

                # `save_transcript()` ne lit pas l'audio, il ne se sert de ce
                # chemin que pour nommer sa sortie — c'est justement ce qui
                # permet de le nommer sans reconstruire la convention ici. Le
                # fichier temporaire, lui, n'existe plus depuis longtemps.
                horodatage = datetime.now().strftime("%Y-%m-%d-%Hh%M")
                state["path"] = save_transcript(
                    state["text"], f"dictee-{horodatage}.wav"
                )
            st.success(f"Transcription enregistrée : {state['path']}")

    # Proposé dans les trois cas, y compris quand rien n'a été transcrit : une
    # dictée inaudible est autant une impasse qu'une réussie, et c'est le seul
    # moyen d'en relancer une.
    st.button("Nouvelle dictée", key="dictation_reset", on_click=_reset_dictation)


def _tab_youtube() -> None:
    url = st.text_input("URL de la vidéo", key="youtube_url", placeholder="https://youtu.be/…")
    options = _audio_options("youtube")

    if st.button(
        "Transcrire", key="youtube_run", type="primary", disabled=not url.strip()
    ):
        from youtube import transcribe_youtube

        # Comme dans `cli.py` : les kwargs partent vers `diarize_file()` ou vers
        # `transcribe_file()` selon le mode, ils ne sont pas interchangeables.
        extra: dict = {"num_speakers": options["num_speakers"]} if options["diarize"] else {}
        if options["language"] and not options["diarize"]:
            extra["language"] = options["language"]

        try:
            with st.spinner("Téléchargement de l'audio, puis transcription…"):
                _, output_path = transcribe_youtube(
                    url.strip(), diarize=options["diarize"], **extra
                )
            st.session_state["youtube"] = _result_from_output(output_path, options)
        except (FileNotFoundError, ValueError) as error:
            st.session_state["youtube"] = None
            st.error(str(error))

    _render_result("youtube")


def main() -> None:
    st.set_page_config(page_title="Whisper Toolkit", page_icon="🎙️", layout="centered")

    # Lancée autrement que depuis un shell interactif — app Automator, Finder,
    # launchd —, l'interface hérite d'un PATH minimal sans `/opt/homebrew/bin`.
    # ffmpeg est alors installé mais introuvable pour les sous-processus de
    # mlx_whisper et whisperx, qui l'appellent par son nom nu. Réparé ici, au
    # point d'entrée concerné : le CLI, lui, part toujours d'un shell.
    ffmpeg = ensure_on_path()

    st.title("🎙️ Whisper Toolkit")
    st.caption(
        "Transcription audio locale — la même chose que `python src/cli.py`, "
        "dans le navigateur. Les sorties sont écrites dans `output/`."
    )

    if not ffmpeg:
        # Sans ça, l'absence de ffmpeg ne se voit qu'au fond d'une trace, une
        # fois le fichier déposé et le modèle chargé.
        st.error(
            "ffmpeg est introuvable — aucune transcription ne fonctionnera.\n\n"
            "Installe-le (`brew install ffmpeg`), ou lance l'app depuis un "
            "terminal où `ffmpeg` répond."
        )

    single, batch, youtube, dictation = st.tabs(
        ["Fichier unique", "Dossier (batch)", "YouTube", "Dictée rapide"]
    )

    with single:
        _tab_single()
    with batch:
        _tab_batch()
    with youtube:
        _tab_youtube()
    with dictation:
        _tab_dictation()


if __name__ == "__main__":
    main()
