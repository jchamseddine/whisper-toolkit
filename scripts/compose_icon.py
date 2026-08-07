"""Recadrage du glyphe rendu, puis centrage sur une toile d'icône 1024.

`render_emoji.swift` dessine volontairement petit dans une grande toile pour ne
rien rogner : le glyphe se retrouve donc décentré, entouré de vide, à une
échelle qui dépend de la police. Impossible d'en tirer directement une icône.

Ce module rattrape ça en se fiant au seul repère fiable — la bounding box du
canal alpha, c'est-à-dire les pixels réellement dessinés. Le glyphe est ramené à
`CONTENT` px puis centré, ce qui rend le résultat indépendant de la taille de
police choisie en amont.

usage : python compose_icon.py <source.png> <sortie.png>
"""

import sys

from PIL import Image

CANVAS = 1024
# macOS laisse respirer les icônes de forme libre : sans cette marge, l'icône
# paraît plus grosse que ses voisines dans le Dock.
CONTENT = 840
# Les pixels quasi transparents sont du halo d'anticrénelage, pas du dessin.
# Les compter élargirait la bounding box et décalerait le centrage.
SEUIL_ALPHA = 8


def compose(src: str, dst: str) -> None:
    image = Image.open(src).convert("RGBA")
    masque = image.getchannel("A").point(lambda v: 255 if v > SEUIL_ALPHA else 0)
    bbox = masque.getbbox()
    if bbox is None:
        raise SystemExit(f"{src} : aucun pixel dessiné, rien à recadrer")

    glyphe = image.crop(bbox)
    echelle = CONTENT / max(glyphe.size)
    glyphe = glyphe.resize(
        (round(glyphe.width * echelle), round(glyphe.height * echelle)),
        Image.LANCZOS,
    )

    icone = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    icone.paste(glyphe, ((CANVAS - glyphe.width) // 2, (CANVAS - glyphe.height) // 2))
    icone.save(dst)
    print(f"écrit {dst} (recadrage {bbox}, glyphe {glyphe.size})")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage : python compose_icon.py <source.png> <sortie.png>")
    compose(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
