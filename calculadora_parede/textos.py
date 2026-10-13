"""Mensagens bilíngues (português e inglês) usadas em toda a calculadora."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Texto:
    """Um texto nos dois idiomas da calculadora."""

    pt: str
    en: str

    def em(self, idioma: str) -> str:
        return self.en if idioma == "en" else self.pt


@dataclass(frozen=True)
class Mensagem:
    """Erro ou aviso de validação, com o campo de entrada a que se refere."""

    nivel: str  # "erro" ou "aviso"
    campo: str
    texto: Texto
