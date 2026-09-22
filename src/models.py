from dataclasses import dataclass, field


@dataclass(frozen=True)
class Recipe:
    """Uma receita ja validada.

    Os campos seguem o template de caderno em duas folhas A5 (ver
    templates/recipe.html): titulo, ingredientes e passos sao obrigatorios; o
    resto so aparece quando o texto de origem o refere e, se faltar, fica em
    branco no PDF -- como no caderno impresso, para se escrever a mao.

    Difficulty e Rating do template nao estao aqui de proposito: sao juizos
    de quem cozinha, nao dados do post, e ficam sempre por preencher.
    """

    title: str
    ingredients: tuple[str, ...]
    steps: tuple[str, ...]
    time: str = ""  # Prep time
    cook_time: str = ""  # Cook time
    temperature: str = ""  # Temp
    servings: str = ""  # Serves
    source: str = ""  # Recipe from
    notes: str = ""  # Notes (alem da caracteristica vinda das tags)
    tags: tuple[str, ...] = field(default_factory=tuple)
    image: str = ""
    source_file: str = ""
