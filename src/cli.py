"""CLI unifié : une commande, une sous-commande par mode d'entrée.

Couche d'orchestration pure, au même titre que `batch.py` : aucune logique de
transcription, de diarisation, de téléchargement ni de résumé n'est écrite ici.
Chaque sous-commande appelle les fonctions des modules qui les portent, puis
affiche ce qu'elles ont produit.

Les imports sont plats parce que ce module s'exécute comme un script
(`python src/cli.py`), ce qui place `src/` en tête de `sys.path`.

Les modules frères sont importés **dans** les fonctions qui en ont besoin, pas
en tête de fichier : importer `youtube` tire yt-dlp, et `diarize`/`batch`
tirent nltk, soit ~0,7 s payées à chaque lancement — y compris pour `--help` ou
pour un résumé, qui n'en ont que faire. Même raison que les imports paresseux
de `mlx_whisper`, `whisperx` et `anthropic` ailleurs dans le toolkit.
"""

import argparse
import os
import sys

# `transcribe` est gratuit à l'import (stdlib seule, mlx_whisper est paresseux)
# et `summarize` ne tire que dotenv ; leurs constantes servent dès la
# construction du parseur.
from summarize import DEFAULT_MODEL as DEFAULT_SUMMARY_MODEL
from summarize import DEFAULT_STYLE, save_summary, summarize_text, summary_path
from transcribe import (
    SUPPORTED_EXTENSIONS,
    save_transcript,
    transcribe_file,
    transcript_path,
)


def _warn_ignored_options(args: argparse.Namespace) -> None:
    """Prévient quand une option n'aura aucun effet dans le mode demandé.

    Les trois entrées audio partagent le même jeu d'options, mais toutes ne
    s'appliquent pas aux deux modes. Un avertissement vaut mieux qu'un
    paramètre silencieusement ignoré.
    """
    if args.num_speakers is not None and not args.diarize:
        print("Attention : --num-speakers est ignoré sans --diarize.", file=sys.stderr)

    if args.language and args.diarize:
        print(
            "Attention : --language est ignoré avec --diarize "
            "(whisperx détecte la langue lui-même).",
            file=sys.stderr,
        )


def _show_transcript(output_path: str) -> None:
    """Affiche la transcription telle qu'elle vient d'être écrite.

    Relire le fichier plutôt que remettre en forme les segments en mémoire
    évite de redéfinir ici le format `[SPEAKER_XX] texte`, qui appartient à
    `diarize.py`.
    """
    with open(output_path, encoding="utf-8") as f:
        print(f.read().rstrip("\n"))

    print(f"\nTranscription enregistrée : {output_path}", file=sys.stderr)


def _summarize_transcript(transcript_file: str, model: str, style: str) -> str:
    """Résume un fichier de transcription et écrit le résumé à côté."""
    with open(transcript_file, encoding="utf-8") as f:
        text = f.read()

    summary = summarize_text(text, model=model, style=style)
    print(summary)

    output_path = save_summary(summary, transcript_file)
    print(f"\nRésumé enregistré : {output_path}", file=sys.stderr)
    return output_path


def summarize_batch(
    summary: dict,
    diarize: bool = False,
    force: bool = False,
    model: str = DEFAULT_SUMMARY_MODEL,
    style: str = DEFAULT_STYLE,
) -> int:
    """Résume les transcriptions d'un lot. Retourne le nombre d'échecs.

    Les fichiers sautés par la reprise sont inclus : leur transcription existe,
    elle est donc résumable — sans quoi un lot repris ne résumerait que les
    fichiers qui restaient à traiter. Un résumé déjà présent est sauté à son
    tour, sauf `force` : chaque appel à l'API se paie.

    Un résumé en échec n'interrompt pas la série, comme pour le lot lui-même.

    Prend des paramètres explicites et non le `Namespace` d'argparse, comme
    `batch.report_summary()` : c'est ce qui la rend appelable depuis `app.py`,
    qui n'a pas de ligne de commande à lui passer. La règle de reprise des
    résumés n'a ainsi qu'une définition, valable pour les deux points d'entrée.
    """
    from diarize import diarized_transcript_path

    path_of = diarized_transcript_path if diarize else transcript_path
    transcripts = sorted(path_of(path) for path in summary["success"] + summary["skipped"])

    failed = 0
    for transcript_file in transcripts:
        expected_summary = summary_path(transcript_file)
        if not force and os.path.isfile(expected_summary):
            print(f"Résumé sauté — déjà présent : {expected_summary}", file=sys.stderr)
            continue

        print(f"\nRésumé de {os.path.basename(transcript_file)}", file=sys.stderr)
        try:
            _summarize_transcript(transcript_file, model, style)
        except ValueError as error:
            failed += 1
            print(f"Erreur : {error}", file=sys.stderr)

    return failed


def _run_transcribe(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    if args.diarize:
        from diarize import diarize_file, save_diarized_transcript

        segments = diarize_file(args.audio_path, num_speakers=args.num_speakers)
        output_path = save_diarized_transcript(segments, args.audio_path)
    else:
        text = transcribe_file(args.audio_path, language=args.language)
        output_path = save_transcript(text, args.audio_path)

    _show_transcript(output_path)

    if args.summarize:
        _summarize_transcript(output_path, args.summary_model, args.summary_style)

    return 0


def _run_batch(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    from batch import process_folder, report_summary

    summary = process_folder(
        args.folder_path,
        diarize=args.diarize,
        num_speakers=args.num_speakers,
        force=args.force,
        language=args.language,
    )
    report_summary(summary)
    exit_code = 1 if summary["failed"] else 0

    if args.summarize and summarize_batch(
        summary,
        diarize=args.diarize,
        force=args.force,
        model=args.summary_model,
        style=args.summary_style,
    ):
        exit_code = 1

    return exit_code


def _run_youtube(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    from youtube import transcribe_youtube

    # `transcribe_youtube` route ses kwargs vers `diarize_file()` ou
    # `transcribe_file()` selon le mode : ils ne sont pas interchangeables.
    extra: dict = {"num_speakers": args.num_speakers} if args.diarize else {}
    if args.language and not args.diarize:
        extra["language"] = args.language

    _, output_path = transcribe_youtube(args.url, diarize=args.diarize, **extra)
    _show_transcript(output_path)

    if args.summarize:
        _summarize_transcript(output_path, args.summary_model, args.summary_style)

    return 0


def _run_summarize(args: argparse.Namespace) -> int:
    if not os.path.isfile(args.transcript_path):
        raise FileNotFoundError(f"Fichier introuvable : {args.transcript_path}")

    _summarize_transcript(args.transcript_path, args.model, args.style)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    # `prog` est la commande réellement tapée : le toolkit n'est pas installé
    # comme exécutable, voir README (« Pourquoi pas une commande installée »).
    parser = argparse.ArgumentParser(
        prog="python src/cli.py",
        description="Transcription audio locale : un fichier, un dossier ou une URL YouTube.",
        epilog=(
            "Exemples :\n"
            "  python src/cli.py transcribe cours.m4a\n"
            "  python src/cli.py transcribe reunion.wav --diarize --num-speakers 3 --summarize\n"
            "  python src/cli.py batch mes-cours/ --language fr\n"
            "  python src/cli.py youtube 'https://youtu.be/...' --summarize\n"
            "  python src/cli.py summarize output/cours.txt --style 'en trois puces'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Options communes aux trois entrées audio. Un seul parseur parent plutôt
    # que trois copies : une option ajoutée ici l'est partout à la fois.
    audio = argparse.ArgumentParser(add_help=False)
    audio.add_argument(
        "--diarize",
        action="store_true",
        help="Identifier les locuteurs (whisperx) au lieu d'une simple transcription",
    )
    audio.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Nombre exact de locuteurs, si connu (avec --diarize)",
    )
    audio.add_argument(
        "--language",
        default=None,
        help="Forcer la langue (ex. fr, en), sans effet avec --diarize. "
        "Par défaut : détection automatique",
    )
    audio.add_argument(
        "--summarize",
        action="store_true",
        help="Enchaîner un résumé de la transcription via l'API Claude (appel payant)",
    )
    audio.add_argument(
        "--summary-model",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Modèle Claude pour --summarize (défaut : {DEFAULT_SUMMARY_MODEL})",
    )
    audio.add_argument(
        "--summary-style",
        default=DEFAULT_STYLE,
        help=f"Style du résumé, en toutes lettres (défaut : {DEFAULT_STYLE})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMANDE")

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        parents=[audio],
        help="Transcrire un fichier audio",
        description="Transcrit un fichier audio en local.",
    )
    transcribe_parser.add_argument(
        "audio_path",
        help=f"Fichier audio à transcrire ({', '.join(SUPPORTED_EXTENSIONS)})",
    )
    transcribe_parser.set_defaults(handler=_run_transcribe)

    batch_parser = subparsers.add_parser(
        "batch",
        parents=[audio],
        help="Transcrire tous les fichiers audio d'un dossier",
        description="Transcrit tous les fichiers audio d'un dossier, en reprenant "
        "là où un lot précédent s'était arrêté.",
    )
    batch_parser.add_argument("folder_path", help="Dossier contenant les fichiers audio")
    batch_parser.add_argument(
        "--force",
        action="store_true",
        help="Retraiter les fichiers dont la sortie existe déjà, résumés compris "
        "(par défaut : reprise, ces fichiers sont sautés)",
    )
    batch_parser.set_defaults(handler=_run_batch)

    youtube_parser = subparsers.add_parser(
        "youtube",
        parents=[audio],
        help="Transcrire l'audio d'une vidéo YouTube",
        description="Télécharge l'audio d'une vidéo YouTube, puis le transcrit.",
    )
    youtube_parser.add_argument("url", help="URL de la vidéo")
    youtube_parser.set_defaults(handler=_run_youtube)

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Résumer une transcription déjà produite",
        description="Résume une transcription déjà produite, via l'API Claude. "
        "Prend un fichier texte, jamais de l'audio.",
    )
    summarize_parser.add_argument(
        "transcript_path", help="Fichier texte à résumer (pas un fichier audio)"
    )
    summarize_parser.add_argument(
        "--model",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Modèle Claude (défaut : {DEFAULT_SUMMARY_MODEL})",
    )
    summarize_parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        help=f"Style du résumé, en toutes lettres (défaut : {DEFAULT_STYLE})",
    )
    summarize_parser.set_defaults(handler=_run_summarize)

    return parser


def main() -> None:
    args = _build_parser().parse_args()

    try:
        exit_code = args.handler(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        # Les mêmes exceptions que celles interceptées par les CLI des modules :
        # elles portent déjà un message actionnable, pas une trace.
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
