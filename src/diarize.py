"""Diarisation (qui parle quand) via whisperx.

Pipeline distinct de `transcribe.py` : whisperx s'appuie sur faster-whisper
(backend CTranslate2), qui n'a pas de support Metal — tout tourne donc sur CPU
ici, contrairement à la transcription mlx-whisper.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

DEFAULT_MODEL = "large-v3"
TOKEN_ENV_VAR = "HF_TOKEN"

# CTranslate2 ne gère ni Metal ni MPS : CPU obligatoire. int8 plutôt que le
# float32 par défaut, sinon large-v3 sur CPU est très lent.
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

TOKEN_HELP = (
    f"Token Hugging Face manquant ou refusé.\n"
    f"1. Crée un token sur https://huggingface.co/settings/tokens\n"
    f"2. Accepte les conditions du modèle "
    f"https://huggingface.co/pyannote/speaker-diarization-community-1\n"
    f"3. Renseigne-le dans un fichier .env à la racine du projet :\n"
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
        raise ValueError(TOKEN_HELP)

    return token


def diarize_file(
    audio_path: str,
    hf_token: str | None = None,
    model: str = DEFAULT_MODEL,
    num_speakers: int | None = None,
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
        diarize_pipeline = DiarizationPipeline(token=token, device=DEVICE)
    except Exception as error:
        # pyannote remonte selon les cas une erreur HTTP, ou un None qui casse
        # au .to(device) : dans les deux cas c'est le token ou l'acceptation
        # des conditions du modèle qui manque.
        raise ValueError(f"{TOKEN_HELP}\n\nDétail : {error}") from error

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
    args = parser.parse_args()

    try:
        segments = diarize_file(
            args.audio_path, model=args.model, num_speakers=args.num_speakers
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
