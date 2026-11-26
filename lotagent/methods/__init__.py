"""Registre des méthodes statistiques applicables à un historique de tirages."""

from .base import Method
from .core import (
    Chi2HotMethod,
    ColdMethod,
    FrequencyMethod,
    MarkovMethod,
    PairMethod,
    TrendMethod,
    UniformMethod,
)

REGISTRY: dict[str, type[Method]] = {
    cls.name: cls
    for cls in (
        FrequencyMethod,
        TrendMethod,
        Chi2HotMethod,
        ColdMethod,
        PairMethod,
        MarkovMethod,
        UniformMethod,
    )
}


def all_method_names() -> list[str]:
    return list(REGISTRY)


def get_methods(names: list[str] | None) -> dict[str, Method]:
    """Instancie les méthodes demandées ('all' ou liste de noms)."""
    if names is None or names == ["all"]:
        names = all_method_names()
    methods: dict[str, Method] = {}
    for name in names:
        key = name.strip().lower()
        if key not in REGISTRY:
            raise KeyError(
                f"Méthode inconnue : {name!r}. Disponibles : {', '.join(all_method_names())}"
            )
        methods[key] = REGISTRY[key]()
    return methods
