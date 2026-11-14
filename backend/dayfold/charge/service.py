"""Cartoon generation. Only available when an AI provider is configured."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.client import AIError, active_client
from ..edition.images import to_eink_png
from ..settings import ChargeSettings
from .render import ChargeScript, render_charge

SCRIPT_PROMPT = """Crie a charge do dia para o jornal "{title}" a partir das manchetes abaixo.
Estilo: {style}
Regras: humor leve e inteligente, sem ofensas, sem caricaturar pessoas reais pelo nome
(use papéis genéricos como "Contribuinte", "Cientista", "Ministro"), textos curtos.
Idioma dos textos: {language}.

Responda com JSON:
{{"title": "título curto", "caption": "legenda com a piada", "setting": "lugar curto",
  "characters": [{{"name": "papel", "x": 0.2, "pose": "standing|pointing|arms_up|thinking|shrugging|sitting|running",
    "facing": "left|right", "speech": "fala curta ou null", "hat": "none|top|cap|crown|helmet",
    "size": "small|normal|large"}}],
  "props": [{{"kind": "sign|desk|globe|computer|rocket|cloud|sun|building|chart_up|chart_down|tree|ballot_box|microphone|book|planet",
    "label": "rótulo curto ou null", "x": 0.5}}]}}
Use 1 a 3 personagens (x entre 0.1 e 0.9, sem sobrepor) e até 3 objetos.

Manchetes:
{headlines}
"""


class _ImagePrompt(BaseModel):
    prompt: str = Field(max_length=900)
    caption: str = Field(max_length=200)


IMAGE_PROMPT = """Você é chargista de um jornal clássico. Escolha a notícia mais relevante abaixo e
crie a ideia de uma charge editorial de painel único, com uma piada visual clara.
Escreva um prompt detalhado em inglês para um gerador de imagens: ilustração em preto e branco,
traço de nanquim com hachuras, estilo charge de jornal impresso, alto contraste (vai para tela
e-ink), cena e personagens descritos com precisão, expressões exageradas. Textos dentro da imagem
só se forem essenciais, curtos e em {language} (placas, rótulos), escritos corretamente.
Sem pessoas reais reconhecíveis e sem logotipos. Estilo editorial: {style}
Também escreva uma legenda curta e espirituosa em {language} para ir abaixo da charge.
Responda com JSON: {{"prompt": "...", "caption": "..."}}

Manchetes:
{headlines}
"""


def generate_charge(session: Session, headlines: list[str], newspaper_title: str, language: str,
                    settings: ChargeSettings, dest_dir: Path, log: Callable[[str], None]) -> dict | None:
    ai = active_client(session)
    if ai is None:
        log("Charge habilitada, mas nenhuma IA ativa: charge omitida.")
        return None
    lang = "português do Brasil" if language == "pt" else "English"
    lines = "\n".join(f"- {h}" for h in headlines[:6])
    dest = dest_dir / "charge.png"
    try:
        if settings.mode == "illustrated" and ai.can_generate_images:
            ip = ai.complete_json(IMAGE_PROMPT.format(style=settings.style, language=lang,
                                                      headlines=lines), _ImagePrompt, max_tokens=500)
            log("Gerando charge ilustrada (pode levar 1 a 2 minutos)...")
            raw = ai.generate_image(ip.prompt)
            img = Image.open(io.BytesIO(raw)).convert("L")
            img = ImageOps.autocontrast(img, cutoff=0.5)
            img.thumbnail((1400, 1400), Image.LANCZOS)
            to_eink_png(img, dest)
            return {"mode": "illustrated", "image_path": str(dest), "caption": ip.caption,
                    "script": {"prompt": ip.prompt}}
        if settings.mode == "illustrated":
            log("A IA ativa não gera imagens: usando a charge roteirizada.")
        script = ai.complete_json(
            SCRIPT_PROMPT.format(title=newspaper_title, style=settings.style, language=lang,
                                 headlines=lines),
            ChargeScript, max_tokens=700,
        )
        render_charge(script, dest)
        log(f"Charge desenhada: {script.title}.")
        return {"mode": "structured", "image_path": str(dest), "caption": None,
                "script": script.model_dump()}
    except AIError as exc:
        log(f"Charge falhou: {exc}")
        return None
