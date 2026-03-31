from .linxiaotang import PERSONA_TEXT as linxiaotang_persona
from .human_template import HUMAN_TEMPLATE

# As you add more personas in the future, import them here
# from .another_persona import PERSONA_TEXT as another_persona

PERSONAS = {
    "linxiaotang": linxiaotang_persona,
    # "another_persona": another_persona,
}

__all__ = ["PERSONAS", "HUMAN_TEMPLATE"]
