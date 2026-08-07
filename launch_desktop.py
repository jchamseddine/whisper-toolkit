"""Lance l'interface Streamlit dans une fenêtre native, sans navigateur.

Troisième point d'entrée, après `src/cli.py` et `app.py` — et comme eux, il ne
contient aucune logique métier : il démarre `app.py` puis l'affiche. Rien de ce
qui touche à l'audio ne passe par ici.

Le besoin : `streamlit run app.py` ouvre un onglet de navigateur, ce qui fait de
l'app Automator un raccourci vers Chrome plutôt qu'une application. Ce module
enveloppe donc le serveur dans une fenêtre WebKit (pywebview) et fait en sorte
que le serveur vive et meure avec elle.

Quatre choses sont moins évidentes qu'elles n'en ont l'air :

- **`--server.headless true` est indispensable**, pas cosmétique. Sans ce
  drapeau, Streamlit ouvre lui-même un onglet au démarrage : la fenêtre native
  s'afficherait *en plus* du navigateur, ce qu'on cherche précisément à éviter.
- **Le port est vérifié avant le lancement.** Sans ça, un serveur déjà en place
  sur 8501 répondrait immédiatement au sondage : la fenêtre s'ouvrirait sur
  l'instance étrangère pendant que notre sous-processus meurt en silence,
  faute de port.
- **Streamlit est démarré dans sa propre session** (`start_new_session`) pour
  pouvoir tuer le groupe de processus entier à la fermeture. Terminer le seul
  processus parent laisserait ses enfants tenir le port 8501.
- **L'identité de l'app est corrigée à la main.** pywebview ouvre sa fenêtre
  depuis ce processus Python, qui n'est pas un bundle `.app` : macOS lui prête
  donc l'identité de l'interpréteur — la fusée et le nom « Python ». L'icône et
  le menu se rattrapent, l'infobulle du Dock non ; voir `set_dock_identity()`.

Lancement : `python launch_desktop.py` depuis la racine du dépôt.
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOST = "localhost"
PORT = 8501
URL = f"http://{HOST}:{PORT}"

# Endpoint de santé de Streamlit : il ne répond que lorsque le serveur est
# réellement prêt à servir l'app, là où une socket ouverte ne prouve que
# l'écoute.
HEALTH_URL = f"{URL}/_stcore/health"

# Marge large : le premier démarrage paie l'import de Streamlit et la
# compilation des templates. Au-delà, c'est un échec, pas une lenteur.
STARTUP_TIMEOUT = 15.0
POLL_INTERVAL = 0.25

# Délai laissé à Streamlit pour se fermer sur SIGTERM avant le SIGKILL.
SHUTDOWN_GRACE = 5.0

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

WINDOW_TITLE = "Whisper Toolkit"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# La même image que l'icône de l'app Automator, mais en PNG : NSImage la lit
# directement, là où le .icns viserait le Finder.
DOCK_ICON = os.path.join(PROJECT_ROOT, "assets", "app-icon-1024.png")


def set_dock_identity() -> None:
    """Donne au processus l'icône et le nom de l'app, plutôt que ceux de Python.

    Sans bundle `.app`, macOS identifie ce processus par le bundle de
    l'interpréteur — `org.python.python`, dont l'`Info.plist` fournit la fusée et
    le nom « Python ». PyObjC, déjà installé puisque pywebview en dépend sur
    macOS, permet d'en corriger une partie :

    - `setApplicationIconImage_()` remplace l'icône du Dock. Fiable, vérifié à
      l'écran : la fusée disparaît au profit du micro ;
    - `CFBundleName`, écrit dans le dictionnaire du bundle principal, renomme le
      **menu** de l'app — « Python » devient « Whisper Toolkit » à côté du logo
      Apple. C'est une mutation du dictionnaire vivant du processus courant, pas
      une écriture sur disque : rien n'est modifié hors du processus.

    L'ordre compte pour le nom : il doit être posé **avant** que `NSApplication`
    existe, car c'est à sa création que le menu est construit. D'où l'appel avant
    l'import de `webview`, qui instancie l'application Cocoa.

    **Ce qui résiste : l'infobulle du Dock**, qui affiche encore « Python » au
    survol. Elle ne vient pas du processus mais de LaunchServices, qui lit le
    bundle sur le disque — `CFBundleName` posé à l'exécution arrive trop tard, et
    `NSProcessInfo.setProcessName_()` n'y change rien non plus (essayé, sans
    effet). Même origine pour la deuxième tuile du Dock — l'applet Automator et
    ce processus en occupent chacun une. Corriger l'un ou l'autre demanderait un
    vrai bundle `.app` avec son propre `Info.plist`, c'est-à-dire py2app ; le
    README pèse le pour et le contre.

    Purement cosmétique : tout échec est silencieux, une fenêtre à la mauvaise
    icône valant mieux que pas de fenêtre.
    """
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle
    except ImportError:
        return

    info = NSBundle.mainBundle().infoDictionary()
    if info is not None:
        info["CFBundleName"] = WINDOW_TITLE

    image = NSImage.alloc().initWithContentsOfFile_(DOCK_ICON)
    if image is not None:
        NSApplication.sharedApplication().setApplicationIconImage_(image)


def port_is_taken(host: str, port: int) -> bool:
    """Vrai si quelque chose écoute déjà sur ce port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_streamlit() -> subprocess.Popen:
    """Démarre `streamlit run app.py`, sans navigateur, dans sa propre session."""
    commande = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        HOST,
        "--server.port",
        str(PORT),
        # Empêche Streamlit d'ouvrir un onglet de navigateur de son côté.
        "--server.headless",
        "true",
    ]
    # Les flux restent hérités : lancée par Automator, l'app n'a pas de terminal,
    # et c'est la sortie d'erreur du script qui remonte dans la boîte de dialogue.
    # Rediriger vers un tube rendrait les erreurs de Streamlit invisibles.
    return subprocess.Popen(commande, cwd=PROJECT_ROOT, start_new_session=True)


def wait_until_ready(process: subprocess.Popen, timeout: float) -> bool:
    """Sonde le serveur jusqu'à réponse. Faux si le délai expire ou s'il meurt."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        # Un serveur mort ne répondra jamais : inutile d'attendre le délai plein.
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as reponse:
                if reponse.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(POLL_INTERVAL)
    return False


def stop_streamlit(process: subprocess.Popen) -> None:
    """Termine le serveur et toute sa descendance, sans rien laisser sur le port."""
    if process.poll() is not None:
        return
    try:
        groupe = os.getpgid(process.pid)
    except ProcessLookupError:
        return

    for signal_ in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(groupe, signal_)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=SHUTDOWN_GRACE)
            return
        except subprocess.TimeoutExpired:
            continue


def _quit_on_sigterm(signum, _frame) -> None:
    """Transforme SIGTERM en sortie ordinaire, pour que le `finally` s'exécute.

    Sans ça, un `killall` ou un « Forcer à quitter » tue le lanceur sans dérouler
    sa pile : Streamlit survit alors à son parent et garde le port 8501. Le
    filet reste imparfait — pendant la boucle Cocoa, le signal n'est traité
    qu'au prochain passage par du bytecode Python — mais il couvre le cas
    courant.
    """
    raise SystemExit(128 + signum)


def main() -> int:
    signal.signal(signal.SIGTERM, _quit_on_sigterm)

    if port_is_taken(HOST, PORT):
        print(
            f"Le port {PORT} est déjà occupé : une instance de Whisper Toolkit "
            f"tourne probablement déjà. Ferme-la, ou libère le port avec "
            f"`lsof -i :{PORT}`, puis relance.",
            file=sys.stderr,
        )
        return 1

    serveur = start_streamlit()
    try:
        if not wait_until_ready(serveur, STARTUP_TIMEOUT):
            if serveur.poll() is not None:
                raison = f"le serveur s'est arrêté (code {serveur.returncode})"
            else:
                raison = f"pas de réponse après {STARTUP_TIMEOUT:.0f} s"
            print(
                f"Streamlit n'a pas démarré : {raison}. "
                f"La fenêtre n'a pas été ouverte ; les détails sont au-dessus.",
                file=sys.stderr,
            )
            return 1

        set_dock_identity()

        # Importé ici seulement : pywebview tire tout PyObjC avec lui, et le
        # payer avant de savoir si le serveur répond ne sert à rien.
        import webview

        webview.create_window(
            WINDOW_TITLE,
            URL,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )
        # Bloque jusqu'à la fermeture de la fenêtre par l'utilisateur.
        webview.start()
        return 0
    finally:
        stop_streamlit(serveur)


if __name__ == "__main__":
    sys.exit(main())
