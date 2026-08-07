"""Résumé d'une transcription via l'API Claude.

Étape distincte de la transcription : ce module prend un fichier texte déjà
produit par `transcribe.py`, `diarize.py` ou `batch.py`, jamais de l'audio.
C'est aussi le seul module du toolkit qui sorte de la machine — tout le reste
tourne en local.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Sonnet courant. `claude-opus-5` est plus capable si le besoin s'en fait
# sentir : changer cette constante, ou passer --model, suffit.
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_STYLE = "concis"

API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
CONSOLE_URL = "https://console.anthropic.com/settings/keys"

# Un résumé est court par nature ; la borne sert à éviter une facture surprise
# si le modèle part en digression. La troncature est détectée plus bas.
MAX_TOKENS = 4096

# Garde-fou d'entrée, très en dessous de la fenêtre de contexte du modèle
# (1 M tokens, soit plusieurs millions de caractères). Il ne sert pas à
# protéger l'API mais à transformer un refus distant obscur en erreur locale
# lisible, avant de payer l'appel. Pas de découpage : hors usage actuel.
MAX_INPUT_CHARS = 150_000

MISSING_KEY_HELP = (
    f"Clé API Anthropic introuvable.\n"
    f"1. Crée une clé sur {CONSOLE_URL}\n"
    f"2. Renseigne-la dans un fichier .env à la racine du projet :\n"
    f"       {API_KEY_ENV_VAR}=sk-ant-...\n"
    f"   (.env est déjà ignoré par git)"
)

SYSTEM_PROMPT = """\
Tu résumes des transcriptions audio : réunions, cours, entretiens, notes vocales.

Le texte vient d'un système de reconnaissance vocale. Il peut contenir des mots
mal reconnus, une ponctuation approximative et des marques d'oral (hésitations,
répétitions, phrases interrompues). Lis à travers ces défauts sans les
commenter. Quand le texte est étiqueté par locuteur — des lignes en
`[SPEAKER_00]` —, sers-t'en pour attribuer les propos, en gardant ces
identifiants tels quels : ils ne correspondent à aucun nom connu.

Structure le résumé ainsi :
- une phrase d'ouverture qui dit de quoi il s'agit ;
- les points clés, en liste ;
- les décisions et les actions à retenir, s'il y en a — sinon n'invente pas la
  section.

Reformule dans tes mots plutôt que de recopier des phrases entières. Si un
passage est trop dégradé pour être compris, dis-le au lieu de deviner.

Réponds en français, quelle que soit la langue de la transcription, et donne le
résumé seul, sans préambule ni commentaire sur la tâche."""


def _resolve_api_key(api_key: str | None) -> str:
    """Retourne la clé fournie, sinon celle du .env."""
    if api_key:
        return api_key

    load_dotenv()
    key = os.getenv(API_KEY_ENV_VAR)
    if not key:
        raise ValueError(MISSING_KEY_HELP)

    return key


def _api_error_help(error: Exception) -> str:
    """Traduit une erreur de l'API en message actionnable.

    Le texte de l'exception est repris tel quel pour les cas non prévus : le
    SDK n'y fait jamais figurer la clé, seulement le code et le motif.
    """
    import anthropic

    if isinstance(error, anthropic.AuthenticationError):
        return (
            f"Clé API refusée (HTTP 401).\n"
            f"Elle est invalide, révoquée, ou mal recopiée dans .env.\n"
            f"→ Vérifie ou régénère-la sur {CONSOLE_URL}."
        )

    if isinstance(error, anthropic.PermissionDeniedError):
        return (
            f"Accès refusé (HTTP 403).\n"
            f"La clé est valide mais n'a pas le droit d'appeler ce modèle.\n"
            f"→ Vérifie les permissions de la clé sur {CONSOLE_URL}."
        )

    if isinstance(error, anthropic.NotFoundError):
        return (
            f"Modèle introuvable (HTTP 404).\n"
            f"L'identifiant demandé n'existe pas ou n'est pas accessible.\n"
            f"Détail : {error}"
        )

    if isinstance(error, anthropic.RateLimitError):
        return "Quota dépassé (HTTP 429). Attends quelques instants et relance."

    # Solde épuisé : remonte en 400, pas en 401/403. La clé est valide, donc
    # sans ce cas le message renvoyait vers la régénération d'une clé qui n'a
    # aucun problème.
    if "credit balance is too low" in str(error):
        return (
            "Solde de crédits insuffisant sur le compte Anthropic (HTTP 400).\n"
            "La clé est valide : c'est le compte qui n'a plus de crédits.\n"
            "→ Ajoute des crédits dans Plans & Billing sur console.anthropic.com,\n"
            "  puis relance."
        )

    if isinstance(error, anthropic.APIConnectionError):
        return (
            "Impossible de joindre l'API Anthropic.\n"
            "Vérifie la connexion réseau, puis relance."
        )

    return f"Échec de l'appel à l'API Claude.\nDétail : {error}"


def summarize_text(
    text: str,
    model: str = DEFAULT_MODEL,
    style: str = DEFAULT_STYLE,
    api_key: str | None = None,
) -> str:
    """Résume une transcription et retourne le texte du résumé."""
    if not text.strip():
        raise ValueError("Transcription vide : rien à résumer.")

    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(
            f"Transcription trop longue : {len(text):,} caractères pour un "
            f"maximum de {MAX_INPUT_CHARS:,}.\n"
            f"Découpe le fichier et résume chaque partie séparément.".replace(",", " ")
        )

    key = _resolve_api_key(api_key)

    # Import paresseux, comme pour whisperx et mlx_whisper : le reste du
    # toolkit fonctionne sans le paquet `anthropic`.
    import anthropic

    client = anthropic.Anthropic(api_key=key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=f"{SYSTEM_PROMPT}\n\nStyle attendu pour ce résumé : {style}.",
            messages=[{"role": "user", "content": text}],
        )
    except Exception as error:
        raise ValueError(_api_error_help(error)) from error

    if response.stop_reason == "refusal":
        raise ValueError(
            "Le modèle a refusé de résumer ce contenu.\n"
            "Rien n'a été produit ; la transcription est inchangée."
        )

    summary = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    if response.stop_reason == "max_tokens":
        print(
            f"Attention : résumé tronqué à {MAX_TOKENS} tokens.",
            file=sys.stderr,
        )

    return summary


def summary_path(transcript_path: str, output_dir: str = "output") -> str:
    """Chemin de sortie attendu pour `transcript_path`, sans rien écrire.

    Pendant de `transcribe.transcript_path()` : c'est ce qui permet à `cli.py`
    de savoir qu'un résumé existe déjà, et donc de ne pas repayer un appel à
    l'API pour le refaire.
    """
    stem = os.path.splitext(os.path.basename(transcript_path))[0]
    return os.path.join(output_dir, f"{stem}_summary.txt")


def save_summary(summary: str, audio_path: str, output_dir: str = "output") -> str:
    """Écrit le résumé dans output_dir et retourne le chemin du fichier."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = summary_path(audio_path, output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(summary)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Résume une transcription déjà produite, via l'API Claude."
    )
    parser.add_argument(
        "transcript_path", help="Fichier texte à résumer (pas un fichier audio)"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Modèle Claude (défaut : {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        help=f"Style du résumé, en toutes lettres (défaut : {DEFAULT_STYLE})",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.transcript_path):
        print(f"Erreur : fichier introuvable : {args.transcript_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.transcript_path, encoding="utf-8") as f:
        text = f.read()

    try:
        summary = summarize_text(text, model=args.model, style=args.style)
    except ValueError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    print(summary)

    output_path = save_summary(summary, args.transcript_path)
    print(f"\nRésumé enregistré : {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
