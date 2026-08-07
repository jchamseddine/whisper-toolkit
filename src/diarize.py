"""Diarisation (qui parle quand) via whisperx.

Pipeline distinct de `transcribe.py` : whisperx s'appuie sur faster-whisper
(backend CTranslate2), qui n'a pas de support Metal — tout tourne donc sur CPU
ici, contrairement à la transcription mlx-whisper.
"""

import argparse
import os
import sys

# whisperx appelle `nltk.download('punkt_tab')` pendant l'alignement. Par défaut
# NLTK écrit dans ~/nltk_data ; on veut le cache dans le repo.
#
# `NLTK_DATA` doit être posé AVANT `import nltk`, et pas seulement complété par
# un `nltk.data.path.insert()` après coup : à l'import, nltk.downloader
# construit un singleton `_downloader` dont le dossier de destination est figé
# une fois pour toutes (`Downloader.__init__` → `default_download_dir()`).
# Modifier `nltk.data.path` ensuite corrige la *lecture*, mais plus l'écriture.
#
# Le makedirs n'est pas optionnel non plus : NLTK ne retient un chemin que s'il
# existe et est writable, or `.nltk_data/` est gitignoré donc absent d'un clone.
_NLTK_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".nltk_data")
)
os.makedirs(_NLTK_DATA_DIR, exist_ok=True)
os.environ["NLTK_DATA"] = _NLTK_DATA_DIR

import nltk  # noqa: E402  -- doit suivre NLTK_DATA
from dotenv import load_dotenv  # noqa: E402

# Filet de sécurité : si un autre module a déjà importé nltk, la variable
# d'environnement est arrivée trop tard pour peupler `nltk.data.path`.
if _NLTK_DATA_DIR not in nltk.data.path:
    nltk.data.path.insert(0, _NLTK_DATA_DIR)

DEFAULT_MODEL = "large-v3"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
TOKEN_ENV_VAR = "HF_TOKEN"
TOKENS_URL = "https://huggingface.co/settings/tokens"

# CTranslate2 ne gère ni Metal ni MPS : CPU obligatoire. int8 plutôt que le
# float32 par défaut, sinon large-v3 sur CPU est très lent.
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

MISSING_TOKEN_HELP = (
    f"Token Hugging Face introuvable.\n"
    f"1. Crée un token sur {TOKENS_URL}\n"
    f"2. Renseigne-le dans un fichier .env à la racine du projet :\n"
    f"       {TOKEN_ENV_VAR}=hf_xxxxxxxxxxxxxxxx\n"
    f"   (ou passe-le en argument à diarize_file)"
)


def _resolve_token(hf_token: str | None) -> str:
    """Retourne le token fourni, sinon celui du .env."""
    if hf_token:
        return hf_token

    load_dotenv()
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        raise ValueError(MISSING_TOKEN_HELP)

    return token


def _http_status(error: Exception) -> int | None:
    """Extrait le code HTTP d'une erreur huggingface_hub, si présent."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is not None:
        return status

    # pyannote ré-emballe parfois l'erreur en perdant l'objet `response`.
    message = str(error)
    for code in (401, 403):
        if f"{code} Client Error" in message:
            return code

    return None


def _diarization_error_help(error: Exception, diarization_model: str) -> str:
    """Traduit un échec de chargement pyannote en message actionnable.

    401 et 403 remontent tous deux en `GatedRepoError`, mais appellent des
    corrections opposées : refaire le token, ou accepter les conditions.
    """
    status = _http_status(error)

    if status == 403:
        return (
            f"Accès refusé au modèle {diarization_model} (HTTP 403).\n"
            f"Le token est valide, mais les conditions d'utilisation de ce modèle\n"
            f"n'ont pas été acceptées sur le compte qui le détient.\n"
            f"→ Accepte-les sur https://huggingface.co/{diarization_model}\n"
            f"  (l'accès est accordé immédiatement), puis relance."
        )

    if status == 401:
        return (
            f"Token Hugging Face refusé (HTTP 401).\n"
            f"Il est invalide, expiré, ou n'a pas le droit de lire les dépôts\n"
            f"sous conditions d'accès.\n"
            f"→ Vérifie ou régénère-le sur {TOKENS_URL},\n"
            f"  puis mets à jour {TOKEN_ENV_VAR} dans .env."
        )

    return (
        f"Échec du chargement du modèle de diarisation {diarization_model}.\n"
        f"Détail : {error}"
    )


def diarize_file(
    audio_path: str,
    hf_token: str | None = None,
    model: str = DEFAULT_MODEL,
    num_speakers: int | None = None,
    diarization_model: str = DEFAULT_DIARIZATION_MODEL,
) -> list[dict]:
    """Transcrit, aligne et diarise un fichier audio.

    Retourne une liste de segments `{start, end, text, speaker}`.
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Fichier introuvable : {audio_path}")

    token = _resolve_token(hf_token)

    # Import paresseux : whisperx tire torch et pyannote, plusieurs secondes.
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    audio = whisperx.load_audio(audio_path)

    asr_model = whisperx.load_model(model, DEVICE, compute_type=COMPUTE_TYPE)
    result = asr_model.transcribe(audio)

    align_model, metadata = whisperx.load_align_model(
        language_code=result["language"], device=DEVICE
    )
    result = whisperx.align(result["segments"], align_model, metadata, audio, DEVICE)

    try:
        diarize_pipeline = DiarizationPipeline(
            model_name=diarization_model, token=token, device=DEVICE
        )
    except Exception as error:
        # pyannote remonte une erreur HTTP, ou un None qui casse au .to(device).
        raise ValueError(_diarization_error_help(error, diarization_model)) from error

    diarize_segments = diarize_pipeline(audio, num_speakers=num_speakers)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    return [
        {
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip(),
            "speaker": segment.get("speaker", "UNKNOWN"),
        }
        for segment in result["segments"]
    ]


def save_diarized_transcript(
    segments: list[dict], audio_path: str, output_dir: str = "output"
) -> str:
    """Écrit les segments étiquetés par locuteur et retourne le chemin du fichier."""
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{stem}_diarized.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(f"[{segment['speaker']}] {segment['text']}\n")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcrit et identifie les locuteurs d'un fichier audio (whisperx)."
    )
    parser.add_argument("audio_path", help="Fichier audio à diariser")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Modèle Whisper (défaut : {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Nombre exact de locuteurs, si connu (sinon détecté automatiquement)",
    )
    parser.add_argument(
        "--diarization-model",
        default=DEFAULT_DIARIZATION_MODEL,
        help=f"Modèle de diarisation pyannote (défaut : {DEFAULT_DIARIZATION_MODEL})",
    )
    args = parser.parse_args()

    try:
        segments = diarize_file(
            args.audio_path,
            model=args.model,
            num_speakers=args.num_speakers,
            diarization_model=args.diarization_model,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    for segment in segments:
        print(f"[{segment['speaker']}] {segment['text']}")

    output_path = save_diarized_transcript(segments, args.audio_path)
    print(f"\nTranscription diarisée enregistrée : {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
