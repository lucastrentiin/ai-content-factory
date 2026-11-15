"""Imagens estáticas de personagens (ficha/preview) — referências visuais persistentes."""
from __future__ import annotations

import skia

from app.media.animation.rig import CharacterRig, FaceState, Pose, pose_for


def character_sheet_png(spec: dict, name: str = "", width: int = 900, height: int = 900) -> bytes:
    """Folha com 3 expressões (neutro, feliz, assustado) para referência de consistência."""
    from app.media.animation.text import draw_text_block

    surf = skia.Surface(width, height)
    c = surf.getCanvas()
    c.clear(skia.ColorSetARGB(255, 241, 245, 249))
    rig = CharacterRig(spec)
    for i, (expr, act) in enumerate((("neutral", "idle"), ("happy", "wave"), ("scared", "cower"))):
        pose = pose_for(act, 0.4) if act != "idle" else Pose()
        rig.draw(c, width * (0.2 + 0.3 * i), height * 0.86, height * 0.62, pose, FaceState(expression=expr), 1)
    if name:
        draw_text_block(c, name, width / 2, height * 0.03, width * 0.9, height * 0.07, skia.ColorSetARGB(255, 15, 23, 42))
    return bytes(surf.makeImageSnapshot().encodeToData(skia.EncodedImageFormat.kPNG, 100))
